"""Wire-level (local HTTP server) tests for upload-files content-type routing.

These do NOT hit Huawei Cloud. A real ``RuntimeClient`` (default
``SDK_HMAC_SHA256`` => ``open_ak_sk=False`` => no signing) is pointed at a
local ``ThreadingHTTPServer`` so we can assert the on-the-wire ``Content-Type``
header and request body for each upload shape.

Why this exists: tar uploads must go on the ``application/x-tar`` channel.
Sending a tar as ``application/octet-stream`` made the gateway tear the TLS
connection down before the server could emit a clean error, masking the real
business error (e.g. "no session") behind a low-level ``ssl.SSLError``.
"""

from __future__ import annotations

import io
import json
import socket
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from agentarts.sdk.service.runtime_client import RuntimeClient

SESSION_HEADER = "x-hw-agentarts-session-id"
pytestmark = pytest.mark.integration


class _Recorded:
    def __init__(self, status: int = 200, payload: dict | None = None) -> None:
        self.method: str | None = None
        self.path: str | None = None
        self.headers: dict[str, str] = {}
        self.body: bytes = b""
        self.respond_status = status
        self.respond_json = payload if payload is not None else {"status": "uploaded"}


class _Handler(BaseHTTPRequestHandler):
    recorded: _Recorded

    def log_message(self, *args, **kwargs):
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length:
            return self.rfile.read(length)
        return b""

    def do_POST(self) -> None:
        self.recorded.method = self.command
        self.recorded.path = self.path
        self.recorded.headers = {k.lower(): v for k, v in self.headers.items()}
        self.recorded.body = self._read_body()
        body = json.dumps(self.recorded.respond_json).encode()
        self.send_response(self.recorded.respond_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def local_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    rec = _Recorded()
    _Handler.recorded = rec
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    client = RuntimeClient(data_endpoint=base, verify_ssl=False)
    yield base, client, rec
    server.shutdown()
    server.server_close()


def _make_tar(path: Path, fmt: int = tarfile.USTAR_FORMAT) -> None:
    with tarfile.open(path, "w", format=fmt) as t:
        data = b"hello tar"
        info = tarfile.TarInfo("inside.txt")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))


def _path_query(rec) -> str:
    """Extract the `path` query param the client sent to the upload endpoint."""
    from urllib.parse import parse_qs, urlsplit

    qs = parse_qs(urlsplit(rec.path).query)
    return (qs.get("path") or [""])[0]


def test_single_tar_suffix_routes_to_x_tar(local_server, tmp_path):
    base, client, rec = local_server
    tar_path = tmp_path / "payload.tar"
    _make_tar(tar_path)
    tar_bytes = tar_path.read_bytes()

    result = client.upload_files(
        agent_name="test-agent", session_id="sess-1",
        files=[{"local_file": str(tar_path)}], path="/tmp/",
    )

    assert rec.headers["content-type"] == "application/x-tar"
    assert rec.body == tar_bytes  # body streamed intact
    assert rec.headers[SESSION_HEADER] == "sess-1"
    # x-tar backend extracts into a directory: path must stay "/tmp/", not be
    # turned into "/tmp/payload.tar" (which the gateway rejects with
    # "path must be a directory ending with '/'").
    assert _path_query(rec) == "/tmp/"
    assert result["status"] == "uploaded"


def test_single_tar_path_without_trailing_slash_gets_one(local_server, tmp_path):
    base, client, rec = local_server
    tar_path = tmp_path / "payload.tar"
    _make_tar(tar_path)

    client.upload_files(
        agent_name="test-agent", session_id="sess-1",
        files=[{"local_file": str(tar_path), "path": "/data"}], path="/tmp/",
    )

    # tar requires a directory ending with '/'; ensure it is normalized.
    assert _path_query(rec) == "/data/"


def test_single_non_tar_uses_full_file_path(local_server, tmp_path):
    base, client, rec = local_server
    plain = tmp_path / "notes.txt"
    plain.write_bytes(b"plain")

    client.upload_files(
        agent_name="test-agent", session_id="sess-3",
        files=[{"local_file": str(plain)}], path="/tmp/",
    )

    # octet-stream: path is the full remote file path (dir + filename).
    assert _path_query(rec) == "/tmp/notes.txt"


@pytest.mark.parametrize(
    "fmt,name",
    [
        (tarfile.GNU_FORMAT, "payload.gnu"),
        (tarfile.PAX_FORMAT, "payload.pax"),
    ],
)
def test_tar_detected_by_magic_without_suffix(local_server, tmp_path, fmt, name):
    base, client, rec = local_server
    tar_path = tmp_path / name  # no .tar suffix
    _make_tar(tar_path, fmt=fmt)

    client.upload_files(
        agent_name="test-agent", session_id="sess-2",
        files=[{"local_file": str(tar_path)}], path="/tmp/",
    )

    assert rec.headers["content-type"] == "application/x-tar"


def test_non_tar_stays_octet_stream(local_server, tmp_path):
    base, client, rec = local_server
    plain = tmp_path / "notes.txt"
    plain.write_bytes(b"plain text payload \x00\x01\x02")
    plain_bytes = plain.read_bytes()

    client.upload_files(
        agent_name="test-agent", session_id="sess-3",
        files=[{"local_file": str(plain)}], path="/tmp/",
    )

    assert rec.headers["content-type"] == "application/octet-stream"
    assert rec.body == plain_bytes


def test_compressed_tarball_not_misdetected_as_x_tar(local_server, tmp_path):
    # .tar.gz is gzip, not a raw tar — it must NOT claim application/x-tar.
    import gzip

    gz = tmp_path / "payload.tar.gz"
    with gzip.open(gz, "wb") as fh:
        fh.write(b"not a raw tar")

    base, client, rec = local_server
    client.upload_files(
        agent_name="test-agent", session_id="sess-4",
        files=[{"local_file": str(gz)}], path="/tmp/",
    )

    assert rec.headers["content-type"] == "application/octet-stream"


def test_multipart_mixed_tar_and_plain_assembles_both(local_server, tmp_path):
    tar_path = tmp_path / "payload.tar"
    _make_tar(tar_path)
    plain = tmp_path / "notes.txt"
    plain.write_bytes(b"plain text payload \x00\x01\x02")

    base, client, rec = local_server
    client.upload_files(
        agent_name="test-agent", session_id="sess-5",
        files=[{"local_file": str(tar_path)}, {"local_file": str(plain)}],
        path="/tmp/",
    )

    assert rec.headers["content-type"].startswith("multipart/form-data")
    assert b"payload.tar" in rec.body
    assert b"notes.txt" in rec.body
    assert b"plain text payload" in rec.body


def test_error_response_surfaces_real_message_not_transport_mask(local_server, tmp_path):
    # The original bug: a bad session produced ssl.SSLError (masked) instead of
    # the server's real error. With the correct content-type the server returns
    # a clean HTTP error that upload_files surfaces verbatim.
    tar_path = tmp_path / "payload.tar"
    _make_tar(tar_path)

    base, client, _ = local_server
    rec = _Recorded(status=404, payload={"error": "no session: sess-bad"})
    _Handler.recorded = rec

    with pytest.raises(RuntimeError, match="no session: sess-bad"):
        client.upload_files(
            agent_name="test-agent", session_id="sess-bad",
            files=[{"local_file": str(tar_path)}], path="/tmp/",
        )
