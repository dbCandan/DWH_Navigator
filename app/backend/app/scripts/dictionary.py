"""Import, export or write the template of the dictionary from the command line.

data-dictionary/PRDs/001-dictionary-management Requirement 16, the backend's replacement of the
source's ``vsa dictionary import|export``::

    python -m app.scripts.dictionary import <path|->     # '-' reads the workbook from stdin
    python -m app.scripts.dictionary export <path|->     # '-' writes the workbook to stdout
    python -m app.scripts.dictionary template <path|->

An import follows the screen's rules (size, template checks, same content, the import lock) and
is recorded with no importing user and the channel ``betik``. It writes to the database only: the
running backend keeps its search index until it is rebuilt, and the Sözlük page shows the index
as stale. A refusal is written to standard error with exit code 2. Event lines go to standard
error, so a workbook written to standard output stays intact.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import app.db.base  # noqa: F401  # populate mapper metadata before any write
from app.core import telemetry
from app.core.config import get_settings
from app.core.errors import ApplicationError
from app.core.logging import ApplicationJsonHandler, JsonFormatter, log_event
from app.db.session import async_session_factory, engine
from app.domain.dictionary import FILE_EMPTY_MESSAGE, DictionaryStatus, ImportChannel
from app.infrastructure.excel.reader import MAX_UPLOAD_BYTES
from app.infrastructure.repositories.dictionary_repository import DictionaryRepository
from app.services.analysis.dictionary_workbook import export
from app.services.dictionary_import import (
    DictionaryWorkbookInvalid,
    check_dictionary_workbook,
)
from app.services.dictionary_service import (
    logger,
    new_version,
    write_dictionary_version,
)
from app.services.search_inputs import platform_tenant_id

RESTART_NOTE = (
    "Çalışan uygulama yeni sözlüğü indeks yeniden kurulunca kullanır "
    "(Yönetim → Bakım → İndeksi yeniden kur)."
)
MAX_PRINTED_WARNINGS = 10


class ScriptRefused(Exception):
    """A Turkish message for standard error; the command exits with code 2."""


def _thousands(number: int) -> str:
    return f"{number:,}".replace(",", ".")


def _read_input(path: str) -> tuple[str, bytes]:
    if path == "-":
        data = sys.stdin.buffer.read(MAX_UPLOAD_BYTES + 1)
        name = "sozluk.xlsx"
    else:
        source = Path(path)
        try:
            with source.open("rb") as handle:
                data = handle.read(MAX_UPLOAD_BYTES + 1)
        except OSError:
            raise ScriptRefused(f"Dosya okunamadı: {path}") from None
        name = source.name[:255] or "sozluk.xlsx"
    if len(data) > MAX_UPLOAD_BYTES:
        raise ScriptRefused("Dosya çok büyük (en fazla 20 MB)")
    if not data:
        raise ScriptRefused(FILE_EMPTY_MESSAGE)
    return name, data


def _write_output(path: str, data: bytes) -> None:
    if path == "-":
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        return
    try:
        Path(path).write_bytes(data)
    except OSError:
        raise ScriptRefused(f"Dosya yazılamadı: {path}") from None
    print(f"Yazıldı: {path}")


async def import_dictionary(path: str) -> None:
    started = perf_counter()
    outcome, code, version = "error", "", ""
    with telemetry.dictionary_import_span(ImportChannel.SCRIPT) as span:
        try:
            name, data = _read_input(path)
            try:
                checked = await asyncio.to_thread(check_dictionary_workbook, data)
            except DictionaryWorkbookInvalid as invalid:
                outcome, code = "invalid", "dictionary_workbook_invalid"
                raise ScriptRefused(invalid.message) from None
            span.row_count = checked.row_count
            imported = checked.imported
            version = imported.version
            now = datetime.now(UTC)
            async with async_session_factory() as session:
                tenant_id = await platform_tenant_id(session)
                repository = DictionaryRepository(session)
                if not await repository.try_import_lock():
                    outcome, code = "conflict", "dictionary_import_in_progress"
                    raise ScriptRefused(
                        "Başka bir sözlük içe aktarması sürüyor; bitince yeniden deneyin."
                    )
                active = await repository.version(tenant_id, DictionaryStatus.ACTIVE)
                if active is not None and active.content_digest == imported.digest:
                    outcome = "unchanged"
                    print(f"Değişmedi: içerik etkin sürümle aynı (sürüm {active.version})")
                    return
                try:
                    await write_dictionary_version(
                        session,
                        tenant_id,
                        new_version(
                            checked,
                            source_name=name,
                            channel=ImportChannel.SCRIPT,
                            now=now,
                        ),
                        user_id=None,
                        now=now,
                    )
                except ApplicationError as refused:
                    outcome, code = "conflict", refused.code
                    raise ScriptRefused(refused.message) from None
                await session.commit()
            outcome = "created"
            print(
                f"Aktarıldı: {_thousands(imported.column_count)} kolon · "
                f"{_thousands(imported.object_count)} tablo (sürüm {imported.version})"
            )
            for warning in imported.warnings[:MAX_PRINTED_WARNINGS]:
                print(f"• {warning}")
            print(RESTART_NOTE)
        finally:
            span.outcome = outcome
            log_event(
                logger,
                "dictionary.import",
                outcome=outcome,
                channel=ImportChannel.SCRIPT.value,
                version=version,
                duration_ms=round((perf_counter() - started) * 1000),
                error_code=code,
            )


async def export_dictionary(path: str) -> None:
    async with async_session_factory() as session:
        tenant_id = await platform_tenant_id(session)
        repository = DictionaryRepository(session)
        active = await repository.version(tenant_id, DictionaryStatus.ACTIVE)
        if active is None:
            raise ScriptRefused("Sözlük henüz içe aktarılmadı.")
        objects = await repository.objects(active)
        columns = await repository.columns(active)
    data = await asyncio.to_thread(export, objects, columns)
    log_event(logger, "dictionary.export", kind="dictionary", version=active.version)
    telemetry.record_dictionary_export("dictionary")
    _write_output(path, data)


def write_template(path: str) -> None:
    data = export(None, None)
    log_event(logger, "dictionary.export", kind="template", version="")
    telemetry.record_dictionary_export("template")
    _write_output(path, data)


async def _run(args: argparse.Namespace) -> None:
    try:
        if args.command == "import":
            await import_dictionary(args.path)
        elif args.command == "export":
            await export_dictionary(args.path)
        else:
            write_template(args.path)
    finally:
        # The pooled connections belong to this command's event loop; close them with it.
        await engine.dispose()


def _configure_logging() -> None:
    import logging

    handler = ApplicationJsonHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(get_settings().log_level.upper())


def main() -> None:
    parser = argparse.ArgumentParser(description="Import or export the data dictionary")
    parser.add_argument("command", choices=("import", "export", "template"))
    parser.add_argument("path", help="workbook path, or '-' for standard input/output")
    args = parser.parse_args()
    _configure_logging()
    try:
        asyncio.run(_run(args))
    except ScriptRefused as refused:
        print(str(refused), file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
