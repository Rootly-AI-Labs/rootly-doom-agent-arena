import io
from types import SimpleNamespace

import doom_arena_mcp as mcp


def _install_stdin(monkeypatch, payload: bytes) -> None:
    monkeypatch.setattr(mcp.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload)))


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
    _install_stdin(monkeypatch, payload)

    message = mcp.read_message()

    assert message["params"]["arguments"]["plan_note"] == plan_note
    assert mcp.MCP_OUTPUT_FRAMING == "content-length"
