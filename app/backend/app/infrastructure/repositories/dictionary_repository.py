"""Persistence of dictionary versions and their records (data-dictionary 001).

Records are read back in the workbook's shape: every template field under its template name, then
the version's extra columns in header order (empty: ''), exactly as the source's ``_texts`` gives
them. A new version is written in one transaction: the previous version is pruned (its records
deleted, its row soft-deleted), the active one becomes previous and the new one active.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionary import DictionaryStatus
from app.domain.models.dictionary import (
    COLUMN_FIELD_COLUMNS,
    OBJECT_FIELD_COLUMNS,
    DictionaryColumnRecord,
    DictionaryObjectRecord,
    DictionaryVersion,
)
from app.domain.models.user import User

# One PostgreSQL advisory lock serialises every dictionary write, from the screen and the script
# alike (Requirement 8); it is held only by the writing transaction.
IMPORT_LOCK_KEY = 0x64776E7644696374  # "dwnvDict"
_EXTRA_CELLS = "extra_cells"

Record = dict[str, str]


@dataclass(frozen=True, slots=True)
class NewDictionaryVersion:
    """A checked workbook, ready to be written as the tenant's active version."""

    version: str
    content_digest: str
    source_name: str
    channel: str
    imported_at: datetime
    row_count: int
    column_count: int
    object_count: int
    warnings: Sequence[str]
    warning_count: int
    objects: Sequence[Mapping[str, str]]
    columns: Sequence[Mapping[str, str]]
    object_extra_headers: Sequence[str]
    column_extra_headers: Sequence[str]


@dataclass(frozen=True, slots=True)
class PrunedVersion:
    version: str
    objects: int
    columns: int


@dataclass(frozen=True, slots=True)
class TableCount:
    database: str
    schema: str
    object: str
    columns: int

    @property
    def key(self) -> str:
        return f"{self.database}.{self.schema}.{self.object}"


def _record(row: Sequence[Any], fields: Sequence[str], extra_headers: Sequence[str]) -> Record:
    values = {field: str(value) for field, value in zip(fields, row, strict=False)}
    extra: Mapping[str, Any] = (row[len(fields)] or {}).get(_EXTRA_CELLS, {})
    for header in extra_headers:
        values[header] = str(extra.get(header, ""))
    return values


def _row(
    record: Mapping[str, str], columns: Mapping[str, str], extra_headers: Sequence[str]
) -> dict[str, Any]:
    row: dict[str, Any] = {column: record.get(field, "") for field, column in columns.items()}
    extra = {h: record[h] for h in extra_headers if record.get(h)}
    row["props"] = {_EXTRA_CELLS: extra} if extra else {}
    return row


class DictionaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def version(
        self, tenant_id: int, status: DictionaryStatus, *, for_update: bool = False
    ) -> DictionaryVersion | None:
        statement = select(DictionaryVersion).where(
            DictionaryVersion.tenant_id == tenant_id,
            DictionaryVersion.status == status.value,
            DictionaryVersion.is_deleted.is_(False),
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def try_import_lock(self) -> bool:
        """Take the import lock for this transaction; False at once when someone holds it."""

        result = await self.session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK_KEY}
        )
        return bool(result.scalar_one())

    async def objects(self, version: DictionaryVersion) -> list[Record]:
        model = DictionaryObjectRecord
        columns = [getattr(model, column) for column in OBJECT_FIELD_COLUMNS.values()]
        rows = await self.session.execute(
            select(*columns, model.props)
            .where(model.dictionary_version_id == version.dictionary_version_id)
            .order_by(model.position)
        )
        fields = list(OBJECT_FIELD_COLUMNS)
        return [_record(row, fields, version.object_extra_headers) for row in rows.all()]

    async def columns(self, version: DictionaryVersion) -> list[Record]:
        model = DictionaryColumnRecord
        columns = [getattr(model, column) for column in COLUMN_FIELD_COLUMNS.values()]
        rows = await self.session.execute(
            select(*columns, model.props)
            .where(model.dictionary_version_id == version.dictionary_version_id)
            .order_by(model.position)
        )
        fields = list(COLUMN_FIELD_COLUMNS)
        return [_record(row, fields, version.column_extra_headers) for row in rows.all()]

    async def table_columns(self, version: DictionaryVersion, key: str) -> list[Record]:
        """The Kolonlar records whose ``DB.Schema.Object`` is ``key``, in sheet order."""

        model = DictionaryColumnRecord
        columns = [getattr(model, column) for column in COLUMN_FIELD_COLUMNS.values()]
        table = model.database_name + "." + model.schema_name + "." + model.object_name
        rows = await self.session.execute(
            select(*columns, model.props)
            .where(
                model.dictionary_version_id == version.dictionary_version_id,
                table == key,
            )
            .order_by(model.position)
        )
        fields = list(COLUMN_FIELD_COLUMNS)
        return [_record(row, fields, version.column_extra_headers) for row in rows.all()]

    async def table_counts(self, version: DictionaryVersion) -> list[TableCount]:
        model = DictionaryColumnRecord
        rows = await self.session.execute(
            select(model.database_name, model.schema_name, model.object_name, func.count())
            .where(model.dictionary_version_id == version.dictionary_version_id)
            .group_by(model.database_name, model.schema_name, model.object_name)
        )
        return [TableCount(str(d), str(s), str(o), int(n)) for d, s, o, n in rows.all()]

    async def importers(self, user_ids: set[int]) -> dict[int, tuple[str, str]]:
        """``user_id -> (public_id, display_name)`` of the importing accounts."""

        if not user_ids:
            return {}
        rows = await self.session.execute(
            select(User.user_id, User.public_id, User.display_name).where(
                User.user_id.in_(user_ids)
            )
        )
        return {int(uid): (str(pid), str(name)) for uid, pid, name in rows.all()}

    async def write_version(
        self,
        tenant_id: int,
        new: NewDictionaryVersion,
        *,
        user_id: int | None,
        now: datetime,
    ) -> tuple[DictionaryVersion, PrunedVersion | None]:
        """Prune the previous version, demote the active one and insert ``new`` as active.

        The caller holds the import lock and owns the transaction.
        """

        pruned: PrunedVersion | None = None
        previous = await self.version(tenant_id, DictionaryStatus.PREVIOUS, for_update=True)
        if previous is not None:
            version_id = previous.dictionary_version_id
            removed_objects = await self.session.execute(
                delete(DictionaryObjectRecord).where(
                    DictionaryObjectRecord.dictionary_version_id == version_id
                )
            )
            removed_columns = await self.session.execute(
                delete(DictionaryColumnRecord).where(
                    DictionaryColumnRecord.dictionary_version_id == version_id
                )
            )
            await self.session.execute(
                update(DictionaryVersion)
                .where(DictionaryVersion.dictionary_version_id == version_id)
                .values(
                    status=DictionaryStatus.PRUNED.value,
                    is_deleted=True,
                    deleted_at=now,
                    deleted_by=user_id,
                    updated_at=now,
                    updated_by=user_id,
                )
            )
            pruned = PrunedVersion(
                previous.version,
                int(getattr(removed_objects, "rowcount", 0) or 0),
                int(getattr(removed_columns, "rowcount", 0) or 0),
            )
        active = await self.version(tenant_id, DictionaryStatus.ACTIVE, for_update=True)
        if active is not None:
            await self.session.execute(
                update(DictionaryVersion)
                .where(DictionaryVersion.dictionary_version_id == active.dictionary_version_id)
                .values(
                    status=DictionaryStatus.PREVIOUS.value,
                    updated_at=now,
                    updated_by=user_id,
                )
            )
        version = DictionaryVersion(
            tenant_id=tenant_id,
            status=DictionaryStatus.ACTIVE.value,
            version=new.version,
            content_digest=new.content_digest,
            source_name=new.source_name,
            channel=new.channel,
            imported_at=now,
            row_count=new.row_count,
            column_count=new.column_count,
            object_count=new.object_count,
            warning_count=new.warning_count,
            warnings=list(new.warnings),
            object_extra_headers=list(new.object_extra_headers),
            column_extra_headers=list(new.column_extra_headers),
            created_at=now,
            updated_at=now,
            created_by=user_id,
            updated_by=user_id,
        )
        self.session.add(version)
        await self.session.flush()
        version_id = version.dictionary_version_id
        object_rows = [
            {
                "dictionary_version_id": version_id,
                "position": position,
                **_row(record, OBJECT_FIELD_COLUMNS, new.object_extra_headers),
            }
            for position, record in enumerate(new.objects)
        ]
        column_rows = [
            {
                "dictionary_version_id": version_id,
                "position": position,
                **_row(record, COLUMN_FIELD_COLUMNS, new.column_extra_headers),
            }
            for position, record in enumerate(new.columns)
        ]
        if object_rows:
            await self.session.execute(insert(DictionaryObjectRecord), object_rows)
        if column_rows:
            await self.session.execute(insert(DictionaryColumnRecord), column_rows)
        return version, pruned
