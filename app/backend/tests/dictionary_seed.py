"""Test-only dictionary seeding: a workbook written as a version, the way the Excel import did.

The product has no dictionary upload any more (dictionary-sync Requirement 13), but the tests still
start from small workbooks and from the synthetic fixture. This module is never imported by
``app``.

- ``seed_through_index`` goes through the search index's change queue: the engine is built from the
  new dictionary first and the version is written only when the build succeeded. The same content
  writes nothing, and a stale index is rebuilt.
- ``seed_behind_index`` writes to the database only, so a running index goes stale.

From a shell, for the browser scenarios on the local stack (``-`` reads the workbook from stdin)::

    python -m tests.dictionary_seed <path|->
"""

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

import app.db.base  # noqa: F401  # populate mapper metadata before any write
from app.db.session import async_session_factory, engine
from app.domain.dictionary import MAX_KEPT_WARNINGS, DictionaryStatus, ImportChannel
from app.infrastructure.repositories.dictionary_repository import (
    DictionaryRepository,
    NewDictionaryVersion,
)
from app.services.analysis.dictionary_workbook import (
    COLUMN_FIELDS,
    OBJECT_FIELDS,
    WorkbookImport,
    from_workbook,
    load_dictionary,
)
from app.services.dictionary_reading import dictionary_identity, identity_digest
from app.services.dictionary_service import write_dictionary_version
from app.services.search_index import (
    ChangePlan,
    IndexTrigger,
    SearchIndex,
    ServingEngine,
)
from app.services.search_inputs import SearchInputs, platform_tenant_id

DEFAULT_NAME = "sozluk.xlsx"


@dataclass(frozen=True, slots=True)
class Seeded:
    """The workbook's version number, and whether a new version was written for it."""

    version: str
    written: bool


def _extra_headers(records: Sequence[Mapping[str, str]], fields: Sequence[str]) -> list[str]:
    return [key for key in records[0] if key not in fields] if records else []


def new_version(
    imported: WorkbookImport, *, source_name: str, channel: ImportChannel, now: datetime
) -> NewDictionaryVersion:
    return NewDictionaryVersion(
        version=imported.version,
        content_digest=imported.digest,
        source_name=source_name,
        channel=channel.value,
        imported_at=now,
        row_count=len(imported.columns),
        column_count=imported.column_count,
        object_count=imported.object_count,
        warnings=imported.warnings[:MAX_KEPT_WARNINGS],
        warning_count=len(imported.warnings),
        objects=imported.objects,
        columns=imported.columns,
        object_extra_headers=_extra_headers(imported.objects, OBJECT_FIELDS),
        column_extra_headers=_extra_headers(imported.columns, COLUMN_FIELDS),
    )


async def seed_through_index(
    index: SearchIndex, data: bytes, *, name: str = DEFAULT_NAME, user_id: int | None = None
) -> Seeded:
    """Build the index from the workbook, then write it; raises what the change queue raises."""

    imported = from_workbook(data)
    tenant_id = await index.tenant_id()
    now = datetime.now(UTC)
    version = new_version(imported, source_name=name, channel=ImportChannel.SCREEN, now=now)
    written = False

    async def plan(inputs: SearchInputs, serving: ServingEngine | None) -> ChangePlan:
        identity = inputs.identity.dictionary
        if identity and identity_digest(identity) == imported.digest:
            if serving is None or serving.identity.dictionary != identity:
                return ChangePlan(inputs=inputs)
            return ChangePlan()
        dictionary = load_dictionary(
            imported.objects, imported.columns, imported.version, imported.digest
        )
        new_inputs = inputs.replace(
            dictionary=dictionary,
            dictionary_identity=dictionary_identity(imported.version, imported.digest),
        )

        async def write(session: AsyncSession) -> None:
            nonlocal written
            await write_dictionary_version(session, tenant_id, version, user_id=user_id, now=now)
            written = True

        return ChangePlan(inputs=new_inputs, write=write)

    await index.change(IndexTrigger.DICTIONARY, plan)
    return Seeded(imported.version, written)


async def seed_behind_index(data: bytes, *, name: str = DEFAULT_NAME) -> Seeded:
    """Write the workbook to the database only, with no user and the channel ``betik``."""

    imported = from_workbook(data)
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        tenant_id = await platform_tenant_id(session)
        active = await DictionaryRepository(session).version(tenant_id, DictionaryStatus.ACTIVE)
        if active is not None and active.content_digest == imported.digest:
            return Seeded(active.version, False)
        await write_dictionary_version(
            session,
            tenant_id,
            new_version(imported, source_name=name, channel=ImportChannel.SCRIPT, now=now),
            user_id=None,
            now=now,
        )
        await session.commit()
    return Seeded(imported.version, True)


async def _run(path: str) -> None:
    if path == "-":
        data, name = sys.stdin.buffer.read(), DEFAULT_NAME
    else:
        data, name = Path(path).read_bytes(), Path(path).name
    try:
        seeded = await seed_behind_index(data, name=name)
    finally:
        # The pooled connections belong to this command's event loop; close them with it.
        await engine.dispose()
    print(f"{'Yazıldı' if seeded.written else 'Değişmedi'}: {seeded.version}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a dictionary workbook (tests only)")
    parser.add_argument("path", help="workbook path, or '-' for standard input")
    asyncio.run(_run(parser.parse_args().path))


if __name__ == "__main__":
    main()
