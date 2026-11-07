"""Export the active data dictionary from the command line.

data-dictionary/PRDs/001-dictionary-management Requirement 16, the backend's replacement of the
source's ``vsa dictionary export``::

    python -m app.scripts.dictionary export <path|->     # '-' writes the workbook to stdout

A refusal is written to standard error with exit code 2. Event lines go to standard error, so a
workbook written to standard output stays intact.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import app.db.base  # noqa: F401  # populate mapper metadata before any write
from app.core import telemetry
from app.core.config import get_settings
from app.core.logging import ApplicationJsonHandler, JsonFormatter, log_event
from app.db.session import async_session_factory, engine
from app.domain.dictionary import DictionaryStatus
from app.infrastructure.repositories.dictionary_repository import DictionaryRepository
from app.services.analysis.dictionary_workbook import export
from app.services.dictionary_service import logger
from app.services.search_inputs import platform_tenant_id


class ScriptRefused(Exception):
    """A Turkish message for standard error; the command exits with code 2."""


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


async def _run(args: argparse.Namespace) -> None:
    try:
        await export_dictionary(args.path)
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
    parser = argparse.ArgumentParser(description="Export the data dictionary")
    parser.add_argument("command", choices=("export",))
    parser.add_argument("path", help="workbook path, or '-' for standard output")
    args = parser.parse_args()
    _configure_logging()
    try:
        asyncio.run(_run(args))
    except ScriptRefused as refused:
        print(str(refused), file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
