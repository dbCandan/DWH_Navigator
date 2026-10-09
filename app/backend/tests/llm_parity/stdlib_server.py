"""A scripted OpenAI-compatible server on 127.0.0.1 that records every request body byte for byte.

Standard library only, so the source client and the target adapter can be driven against the
same server code. It answers ``POST .../chat/completions`` with the scripted answers in order.
"""

import threading
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ScriptedServer:
    def __init__(self, answers: Iterable[tuple[int, str]]) -> None:
        self.bodies: list[bytes] = []
        self._answers = list(answers)
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                with owner._lock:
                    owner.bodies.append(body)
                    status, text = (
                        owner._answers.pop(0) if owner._answers else (500, "script exhausted")
                    )
                payload = text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
                self.close_connection = True

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)
