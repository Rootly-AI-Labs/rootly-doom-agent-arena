from __future__ import annotations

import io
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

import jev_doom_mcp as mcp
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


class FakeController:
    def __init__(self):
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.stop_calls = 0
        self.close_calls = 0

    def prepare(self, participant_id, agent_name=None, control_mode=None):
        self.calls.append(
            (
                "prepare",
                (participant_id,),
                {"agent_name": agent_name, "control_mode": control_mode},
            )
        )
        return {"mode": "prepared", "participant_id": participant_id}

    def run(self, strategic_directive="", max_run_ms=45_000):
        self.calls.append(
            (
                "run",
                (),
                {
                    "strategic_directive": strategic_directive,
                    "max_run_ms": max_run_ms,
                },
            )
        )
        return {"mode": "running", "max_run_ms": max_run_ms}

    def resume(self, strategic_directive="", override_plan=None, max_run_ms=45_000):
        self.calls.append(
            (
                "resume",
                (),
                {
                    "strategic_directive": strategic_directive,
                    "override_plan": override_plan,
                    "max_run_ms": max_run_ms,
                },
            )
        )
        return {"mode": "running", "resumed": True}

    def status(self):
        self.calls.append(("status", (), {}))
        return {"mode": "idle"}

    def stop(self):
        self.stop_calls += 1
        self.calls.append(("stop", (), {}))
        return {"mode": "finished"}

    def close(self):
        self.close_calls += 1
        self.calls.append(("close", (), {}))


def request(message_id: int, method: str, params=None):
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def ndjson_messages(payload: bytes):
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def make_server(controller=None):
    output = io.BytesIO()
    transport = mcp.StdioTransport(io.BytesIO(), output)
    transport.output_framing = "ndjson"
    fake = controller or FakeController()
    return mcp.JevDoomMCPServer(fake, transport), fake, output


def tool_call(message_id: int, name: str, arguments=None):
    return request(
        message_id,
        "tools/call",
        {"name": name, "arguments": arguments or {}},
    )


def test_ndjson_read_and_matching_write_preserve_unicode():
    incoming = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "ping",
        "params": {"note": "Shotgun acquired — appointments cancelled."},
    }
    source = io.BytesIO((json.dumps(incoming, ensure_ascii=False) + "\n").encode("utf-8"))
    output = io.BytesIO()
    transport = mcp.StdioTransport(source, output)

    assert transport.read_message() == incoming
    assert transport.output_framing == "ndjson"
    transport.write_message({"jsonrpc": "2.0", "id": 1, "result": incoming["params"]})

    assert output.getvalue().endswith(b"\n")
    assert ndjson_messages(output.getvalue())[0]["result"] == incoming["params"]


def test_content_length_read_handles_chunked_body_and_matching_write():
    incoming = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "ping",
        "params": {"note": "southern hospitality — with buckshot"},
    }
    body = json.dumps(incoming, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    source = ChunkedStream(
        b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body,
        chunk_size=3,
    )
    output = io.BytesIO()
    transport = mcp.StdioTransport(source, output)

    assert transport.read_message() == incoming
    assert source.read_calls > 1
    assert transport.output_framing == "content-length"
    transport.write_message({"jsonrpc": "2.0", "id": 2, "result": {}})

    header, response_body = output.getvalue().split(b"\r\n\r\n", 1)
    assert header == b"Content-Length: " + str(len(response_body)).encode("ascii")
    assert json.loads(response_body) == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_read_exact_bytes_rejects_truncated_body():
    with pytest.raises(EOFError, match="2 bytes missing"):
        mcp.read_exact_bytes(ChunkedStream(b"abc", chunk_size=1), 5)


def test_initialize_lists_exact_strict_tool_surface():
    server, _, output = make_server()
    assert server.handle_message(
        request(
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        )
    )
    assert server.handle_message(request(2, "tools/list", {}))

    initialize, listing = ndjson_messages(output.getvalue())
    assert initialize["result"]["protocolVersion"] == "2025-06-18"
    assert initialize["result"]["serverInfo"]["name"] == "jev-doom-player"
    tools = listing["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "prepare_jev_player",
        "run_jev_player",
        "resume_jev_player",
        "get_jev_player_status",
        "stop_jev_player",
    ]
    for tool in tools:
        assert tool["inputSchema"]["additionalProperties"] is False
    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["prepare_jev_player"]["inputSchema"]["properties"]["control_mode"][
        "enum"
    ] == ["jev_only", "jev_hybrid"]
    for name in ("run_jev_player", "resume_jev_player"):
        limit = by_name[name]["inputSchema"]["properties"]["max_run_ms"]
        assert limit["minimum"] == 100
        assert limit["maximum"] == 55_000
        directive = by_name[name]["inputSchema"]["properties"]["strategic_directive"]
        assert directive["maxLength"] == 512
    override = by_name["resume_jev_player"]["inputSchema"]["properties"]["override_plan"]
    assert override["additionalProperties"] is False


def test_tools_call_controller_with_defaults_and_validated_override():
    server, controller, output = make_server()
    override = {
        "objective": "hold center",
        "route": ["M06", "M10"],
        "engagement_policy": "engage_if_visible",
        "reasoning": "Safe line through center.",
        "plan_note": "I own the middle now.",
    }
    messages = [
        tool_call(
            1,
            "prepare_jev_player",
            {
                "participant_id": "player_1",
                "agent_name": "Doom Roomba",
                "control_mode": "jev_only",
            },
        ),
        tool_call(2, "run_jev_player", {"strategic_directive": "Hold center"}),
        tool_call(
            3,
            "resume_jev_player",
            {"strategic_directive": "Take the lane", "override_plan": override, "max_run_ms": 500},
        ),
        tool_call(4, "get_jev_player_status"),
        tool_call(5, "stop_jev_player"),
    ]
    for message in messages:
        assert server.handle_message(message)

    responses = ndjson_messages(output.getvalue())
    assert all(response["result"]["isError"] is False for response in responses)
    assert controller.calls[:5] == [
        (
            "prepare",
            ("player_1",),
            {"agent_name": "Doom Roomba", "control_mode": "jev_only"},
        ),
        ("run", (), {"strategic_directive": "Hold center", "max_run_ms": 45_000}),
        (
            "resume",
            (),
            {
                "strategic_directive": "Take the lane",
                "override_plan": override,
                "max_run_ms": 500,
            },
        ),
        ("status", (), {}),
        ("stop", (), {}),
    ]


@pytest.mark.parametrize("max_run_ms", [99, 55_001, True, 1.5, "500"])
def test_max_run_ms_contract_is_enforced_before_controller_call(max_run_ms):
    server, controller, output = make_server()

    server.handle_message(tool_call(1, "run_jev_player", {"max_run_ms": max_run_ms}))

    response = ndjson_messages(output.getvalue())[0]
    assert response["result"]["isError"] is True
    assert not any(call[0] == "run" for call in controller.calls)


def test_unknown_arguments_and_invalid_nested_override_are_rejected():
    server, controller, output = make_server()
    server.handle_message(tool_call(1, "get_jev_player_status", {"extra": True}))
    server.handle_message(
        tool_call(
            2,
            "resume_jev_player",
            {"override_plan": {"route": ["M06"], "plan_note": "Safe", "token": "nope"}},
        )
    )

    responses = ndjson_messages(output.getvalue())
    assert [item["result"]["isError"] for item in responses] == [True, True]
    assert controller.calls == []


def test_invalid_control_mode_is_rejected_before_prepare():
    server, controller, output = make_server()

    server.handle_message(
        tool_call(
            1,
            "prepare_jev_player",
            {"participant_id": "player_1", "control_mode": "unknown"},
        )
    )

    response = ndjson_messages(output.getvalue())[0]
    assert response["result"]["isError"] is True
    assert not any(call[0] == "prepare" for call in controller.calls)


def test_unrelated_cancel_notification_has_no_response_and_does_not_stop_controller():
    server, controller, output = make_server()

    assert server.handle_message(
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": 9, "reason": "client cancelled"},
        }
    )

    assert output.getvalue() == b""
    assert controller.stop_calls == 0
    assert controller.close_calls == 0


@pytest.mark.parametrize("tool_name", ["run_jev_player", "resume_jev_player"])
def test_immediate_matching_cancel_skips_queued_bounded_call(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
):
    cancel_processed = threading.Event()
    original_cancel = mcp.JevDoomMCPServer.cancel_request
    original_handle = mcp.JevDoomMCPServer.handle_message

    def signal_cancel(server, request_id):
        cancelled = original_cancel(server, request_id)
        if request_id == 9:
            cancel_processed.set()
        return cancelled

    def wait_for_cancel(server, message):
        if message.get("method") == "tools/call" and message.get("id") == 9:
            assert cancel_processed.wait(timeout=1), "reader did not process cancellation"
        return original_handle(server, message)

    monkeypatch.setattr(mcp.JevDoomMCPServer, "cancel_request", signal_cancel)
    monkeypatch.setattr(mcp.JevDoomMCPServer, "handle_message", wait_for_cancel)
    incoming = [
        tool_call(9, tool_name, {"max_run_ms": 100}),
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": 9, "reason": "cancel immediately"},
        },
        request(10, "shutdown", {}),
    ]
    source = io.BytesIO(
        "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in incoming).encode()
    )
    output = io.BytesIO()
    controller = FakeController()

    assert mcp.serve(controller, input_stream=source, output_stream=output) == 0

    assert not any(call[0] in {"run", "resume"} for call in controller.calls)
    assert [response["id"] for response in ndjson_messages(output.getvalue())] == [10]


@pytest.mark.parametrize("tool_name", ["run_jev_player", "resume_jev_player"])
def test_immediate_eof_skips_queued_bounded_call(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
):
    eof_processed = threading.Event()
    original_cancel_all = mcp.JevDoomMCPServer.cancel_all_requests
    original_handle = mcp.JevDoomMCPServer.handle_message

    def signal_eof(server):
        cancelled = original_cancel_all(server)
        eof_processed.set()
        return cancelled

    def wait_for_eof(server, message):
        if message.get("method") == "tools/call" and message.get("id") == 9:
            assert eof_processed.wait(timeout=1), "reader did not process EOF"
        return original_handle(server, message)

    monkeypatch.setattr(mcp.JevDoomMCPServer, "cancel_all_requests", signal_eof)
    monkeypatch.setattr(mcp.JevDoomMCPServer, "handle_message", wait_for_eof)
    source = io.BytesIO(
        (json.dumps(tool_call(9, tool_name, {"max_run_ms": 100})) + "\n").encode()
    )
    output = io.BytesIO()
    controller = FakeController()

    assert mcp.serve(controller, input_stream=source, output_stream=output) == 0

    assert not any(call[0] in {"run", "resume"} for call in controller.calls)
    assert output.getvalue() == b""
    assert controller.stop_calls == 1
    assert controller.close_calls == 1


class BlockingLineStream:
    def __init__(self):
        self.lines: queue.Queue[bytes] = queue.Queue()

    def send(self, message):
        self.lines.put(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")

    def close(self):
        self.lines.put(b"")

    def readline(self):
        return self.lines.get(timeout=5)

    def read(self, _size=-1):
        raise AssertionError("NDJSON test stream should not use read()")


class BlockingController(FakeController):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.released = threading.Event()

    def run(self, strategic_directive="", max_run_ms=45_000):
        self.started.set()
        assert self.released.wait(timeout=3), "cancel did not stop the blocking controller"
        return super().run(strategic_directive, max_run_ms)

    def stop(self):
        self.released.set()
        return super().stop()


def test_serve_processes_matching_cancel_while_run_tool_is_blocked():
    source = BlockingLineStream()
    output = io.BytesIO()
    controller = BlockingController()
    result = []
    server_thread = threading.Thread(
        target=lambda: result.append(
            mcp.serve(controller, input_stream=source, output_stream=output)
        )
    )
    server_thread.start()
    source.send(tool_call(9, "run_jev_player", {"max_run_ms": 55_000}))
    assert controller.started.wait(timeout=1), "run tool did not start"
    source.send(
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": 9, "reason": "client cancelled"},
        }
    )
    source.send(request(10, "shutdown", {}))
    source.close()

    server_thread.join(timeout=3)
    assert not server_thread.is_alive()
    assert result == [0]
    assert controller.stop_calls >= 1
    responses = ndjson_messages(output.getvalue())
    assert [response["id"] for response in responses] == [9, 10]


def test_shutdown_and_eof_clean_up_controller():
    server, shutdown_controller, output = make_server()

    assert server.handle_message(request(7, "shutdown", {})) is False
    assert ndjson_messages(output.getvalue())[0]["result"] is None
    assert shutdown_controller.stop_calls == 1
    assert shutdown_controller.close_calls == 1
    server.close()
    assert shutdown_controller.close_calls == 1

    eof_controller = FakeController()
    assert mcp.serve(
        eof_controller,
        input_stream=io.BytesIO(b""),
        output_stream=io.BytesIO(),
    ) == 0
    assert eof_controller.stop_calls == 1
    assert eof_controller.close_calls == 1


def test_ping_resources_prompts_and_unknown_request():
    server, _, output = make_server()
    server.handle_message(request(1, "ping", {}))
    server.handle_message(request(2, "resources/list", {}))
    server.handle_message(request(3, "prompts/list", {}))
    server.handle_message(request(4, "not/a/method", {}))

    responses = ndjson_messages(output.getvalue())
    assert responses[0]["result"] == {}
    assert responses[1]["result"] == {"resources": []}
    assert responses[2]["result"] == {"prompts": []}
    assert responses[3]["error"]["code"] == -32601


def test_subprocess_ndjson_handshake_uses_fake_controller_only():
    scripts_dir = Path(mcp.__file__).resolve().parent
    bootstrap = f"""
import sys
sys.path.insert(0, {str(scripts_dir)!r})
import jev_doom_mcp as mcp

class Fake:
    def prepare(self, participant_id, agent_name=None, control_mode=None): return {{"mode": "prepared"}}
    def run(self, strategic_directive="", max_run_ms=45000): return {{"mode": "running"}}
    def resume(self, strategic_directive="", override_plan=None, max_run_ms=45000): return {{"mode": "running"}}
    def status(self): return {{"mode": "idle"}}
    def stop(self): return {{"mode": "finished"}}
    def close(self): pass

raise SystemExit(mcp.serve(Fake()))
"""
    incoming = [
        request(
            1,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "subprocess", "version": "1"}},
        ),
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        request(2, "tools/list", {}),
        request(3, "shutdown", {}),
    ]
    payload = "".join(json.dumps(message, separators=(",", ":")) + "\n" for message in incoming).encode()

    completed = subprocess.run(
        [sys.executable, "-c", bootstrap],
        input=payload,
        capture_output=True,
        cwd=scripts_dir,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stderr == b""
    responses = ndjson_messages(completed.stdout)
    assert [response["id"] for response in responses] == [1, 2, 3]
    assert responses[0]["result"]["serverInfo"]["name"] == "jev-doom-player"
    assert len(responses[1]["result"]["tools"]) == 5
    assert responses[2]["result"] is None
