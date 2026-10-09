"""The fake model server closes even while a client keeps a connection open.

Python 3.12+ ``asyncio.Server.wait_closed`` waits for every open connection, so a client that keeps
an idle connection (or a request the scenario never answers) would make ``close`` wait forever.
"""

import asyncio

import pytest

from tests.fakes.llm_server import FakeLlmServer, hang

pytestmark = pytest.mark.unit


async def test_close_does_not_wait_for_an_idle_connection() -> None:
    fake = await FakeLlmServer(scenario=hang()).start()
    reader, writer = await asyncio.open_connection("127.0.0.1", fake.port)
    try:
        async with asyncio.timeout(0.5):
            while fake.connections < 1:
                await asyncio.sleep(0.01)
        async with asyncio.timeout(2):
            await fake.close()
        async with asyncio.timeout(2):
            assert await reader.read() == b""
    finally:
        writer.close()


async def test_close_does_not_wait_for_an_unanswered_request() -> None:
    started = asyncio.Event()
    fake = await FakeLlmServer(scenario=hang(started)).start()
    _reader, writer = await asyncio.open_connection("127.0.0.1", fake.port)
    try:
        writer.write(b"POST /v1/chat/completions HTTP/1.1\r\nContent-Length: 2\r\n\r\n{}")
        await writer.drain()
        async with asyncio.timeout(2):
            await started.wait()
        async with asyncio.timeout(2):
            await fake.close()
        async with asyncio.timeout(2):
            while fake.active:
                await asyncio.sleep(0.01)
    finally:
        writer.close()
