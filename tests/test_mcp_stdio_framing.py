import io
from types import SimpleNamespace

import doom_arena_mcp as mcp
import pytest


class ChunkedStream:
    def __init__(self, payload: bytes, chunk_size: int = 2):
        self.stream = io.BytesIO(payload)
        self.chunk_size = chunk_size
        self.read_calls = 0

    def readline(self) -> bytes:
        return self.stream.readline()

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if size < 0:
            size = self.chunk_size
        return self.stream.read(min(size, self.chunk_size))


def _install_stdin(monkeypatch, payload: bytes, *, chunked: bool = False):
    stream = ChunkedStream(payload) if chunked else io.BytesIO(payload)
    monkeypatch.setattr(mcp.sys, "stdin", SimpleNamespace(buffer=stream))
    return stream


def test_read_message_preserves_unicode_in_ndjson(monkeypatch):
    plan_note = "Shotgun acquired; now I’m accepting hostile appointments."
    payload = (
        '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
        '{"name":"set_participant_plan","arguments":{"plan_note":"'
        + plan_note
        + '"}}}\n'
    ).encode("utf-8")
    _install_stdin(monkeypatch, payload)

    message = mcp.read_message()

    assert message["params"]["arguments"]["plan_note"] == plan_note
    assert mcp.MCP_OUTPUT_FRAMING == "ndjson"


def test_read_message_preserves_unicode_with_content_length(monkeypatch):
    plan_note = "I’m bringing southern hospitality north—with buckshot."
    body = (
        '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":'
        '{"name":"set_participant_plan","arguments":{"plan_note":"'
        + plan_note
        + '"}}}'
    ).encode("utf-8")
    payload = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
    stream = _install_stdin(monkeypatch, payload, chunked=True)

    message = mcp.read_message()

    assert message["params"]["arguments"]["plan_note"] == plan_note
    assert mcp.MCP_OUTPUT_FRAMING == "content-length"
    assert stream.read_calls > 1


def test_read_exact_bytes_raises_when_stream_ends_early():
    stream = ChunkedStream(b"abc", chunk_size=1)

    with pytest.raises(EOFError, match="2 bytes missing"):
        mcp.read_exact_bytes(stream, 5)
