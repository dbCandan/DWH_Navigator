"""Excel uploads and downloads at the HTTP boundary (dictionary-management Requirement 2, 15).

An upload's body is the workbook itself (Decision 10): ``Content-Type`` is the ``.xlsx`` type or
``application/octet-stream`` (else 415 ``unsupported_media_type``); the body is read up to 20 MB,
refused at once when ``Content-Length`` declares more and cut off when the stream goes beyond it
(413 ``upload_too_large``); a chunked body is accepted. The file name comes percent-encoded in
``X-Filename``; its folders and control characters are dropped and it is cut to 255 characters.
The body stays in memory. Downloads are produced per request and never cached.
"""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from fastapi import Request, status
from fastapi.responses import Response

from app.core.errors import ApplicationError
from app.infrastructure.excel.reader import MAX_UPLOAD_BYTES
from app.infrastructure.excel.writer import XLSX_MEDIA_TYPE

FILENAME_MAX_LENGTH = 255
ACCEPTED_MEDIA_TYPES = frozenset({XLSX_MEDIA_TYPE, "application/octet-stream"})
UPLOAD_TOO_LARGE_CODE = "upload_too_large"
UNSUPPORTED_MEDIA_TYPE_CODE = "unsupported_media_type"
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# The request body of an upload endpoint in the OpenAPI contract.
EXCEL_REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            media: {"schema": {"type": "string", "format": "binary"}}
            for media in sorted(ACCEPTED_MEDIA_TYPES)
        },
    }
}
# A download response in the OpenAPI contract.
EXCEL_RESPONSE: dict[str, Any] = {
    "description": "Excel çalışma kitabı",
    "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
}


@dataclass(frozen=True, slots=True)
class ExcelUpload:
    filename: str
    data: bytes


def upload_too_large() -> ApplicationError:
    return ApplicationError(
        status.HTTP_413_CONTENT_TOO_LARGE,
        UPLOAD_TOO_LARGE_CODE,
        "Dosya çok büyük (en fazla 20 MB)",
    )


def upload_filename(raw: str | None, default: str) -> str:
    """The workbook's name without folders and control characters, at most 255 characters."""

    name = unquote(raw or "", encoding="utf-8", errors="replace")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _CONTROL.sub("", name).strip()[:FILENAME_MAX_LENGTH].strip()
    return name or default


async def read_excel_upload(request: Request, *, empty_code: str, default_name: str) -> ExcelUpload:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in ACCEPTED_MEDIA_TYPES:
        raise ApplicationError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            UNSUPPORTED_MEDIA_TYPE_CODE,
            "Dosya Excel (.xlsx) olarak gönderilmeli.",
        )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise upload_too_large()
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_UPLOAD_BYTES:
            raise upload_too_large()
    if not body:
        raise ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, empty_code, "Dosya boş")
    return ExcelUpload(
        upload_filename(request.headers.get("x-filename"), default_name), bytes(body)
    )


def excel_download(filename: str, data: bytes) -> Response:
    return Response(
        content=data,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
