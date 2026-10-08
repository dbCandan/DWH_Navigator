"""Workbook uploads at the HTTP boundary (data-dictionary 001-dictionary-management Requirement 2).

The body is the workbook itself: an Excel or octet-stream type, at most 20 MB (by the declared
length and while reading a chunked body), not empty; the percent-encoded ``X-Filename`` loses its
folders and control characters and is cut to 255 characters.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api import excel_transfer
from app.api.excel_transfer import read_excel_upload, upload_filename
from app.core.errors import ApplicationError, install_error_handlers
from app.infrastructure.excel.writer import XLSX_MEDIA_TYPE

pytestmark = pytest.mark.unit


def _app() -> FastAPI:
    application = FastAPI()
    install_error_handlers(application)

    @application.post("/upload")
    async def upload(request: Request) -> dict[str, object]:
        received = await read_excel_upload(
            request, empty_code="x_file_empty", default_name="d.xlsx"
        )
        return {"name": received.filename, "size": len(received.data)}

    return application


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        yield c


def _code(response: object) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]["code"]  # type: ignore[attr-defined]


async def test_excel_and_octet_stream_bodies_are_accepted(client: AsyncClient) -> None:
    for media in (XLSX_MEDIA_TYPE, "application/octet-stream", "Application/Octet-Stream; x=y"):
        response = await client.post(
            "/upload",
            content=b"PK-data",
            headers={"Content-Type": media, "X-Filename": "S%C3%B6zl%C3%BCk.xlsx"},
        )
        assert response.json() == {"name": "Sözlük.xlsx", "size": 7}


async def test_another_type_is_415(client: AsyncClient) -> None:
    for media in ("application/json", "multipart/form-data; boundary=x", ""):
        response = await client.post("/upload", content=b"x", headers={"Content-Type": media})
        assert _code(response) == (415, "unsupported_media_type")


async def test_a_body_over_the_limit_is_413_declared_or_streamed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(excel_transfer, "MAX_UPLOAD_BYTES", 10)
    headers = {"Content-Type": "application/octet-stream"}
    declared = await client.post("/upload", content=b"x" * 11, headers=headers)
    assert _code(declared) == (413, "upload_too_large")
    assert declared.json()["detail"]["message"] == "Dosya çok büyük (en fazla 20 MB)"

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(4):
            yield b"abcd"

    streamed = await client.post("/upload", content=chunks(), headers=headers)
    assert _code(streamed) == (413, "upload_too_large")
    exact = await client.post("/upload", content=b"x" * 10, headers=headers)
    assert exact.status_code == 200


async def test_an_empty_body_has_the_callers_code(client: AsyncClient) -> None:
    response = await client.post(
        "/upload", content=b"", headers={"Content-Type": "application/octet-stream"}
    )
    assert _code(response) == (422, "x_file_empty")
    assert response.json()["detail"]["message"] == "Dosya boş"


def test_the_file_name_loses_folders_and_control_characters() -> None:
    assert upload_filename("C%3A%5Cveri%5CVeriSozlugu.xlsx", "d") == "VeriSozlugu.xlsx"
    assert upload_filename("../../etc/sozluk.xlsx", "d") == "sozluk.xlsx"
    assert upload_filename("a%00b%0Ac%1Fd%7F.xlsx", "d") == "abcd.xlsx"
    assert upload_filename("", "sozluk.xlsx") == "sozluk.xlsx"
    assert upload_filename(None, "sozluk.xlsx") == "sozluk.xlsx"
    assert upload_filename("klasor/", "sozluk.xlsx") == "sozluk.xlsx"
    assert upload_filename("%C3%A7" * 300, "d") == "ç" * 255
    assert upload_filename("%FF.xlsx", "d") == "�.xlsx"


def test_refusals_are_application_errors() -> None:
    error = excel_transfer.upload_too_large()
    assert isinstance(error, ApplicationError) and error.status_code == 413
