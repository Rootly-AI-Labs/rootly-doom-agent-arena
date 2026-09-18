#!/usr/bin/env python3
"""Client-neutral stdio MCP server for the Jev Doom player controller.

Stdout is reserved exclusively for JSON-RPC messages.  The controller import is
lazy so protocol tests can inject a fake without constructing network clients or
reading credentials.
"""

from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
from collections.abc import Mapping
from typing import Any, BinaryIO

SERVER_NAME = "jev-doom-player"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18"})
DEFAULT_MAX_RUN_MS = 45_000
MAX_RUN_MS = 55_000
MCP_OUTPUT_FRAMING = "content-length"
_BOUNDED_TOOL_NAMES = frozenset({"run_jev_player", "resume_jev_player"})

_PARTICIPANT_SCHEMA = {
    "type": "string",
    "enum": ["player_1", "player_2"],
}
_DIRECTIVE_SCHEMA = {
    "type": "string",
    "maxLength": 320,
}
_MAX_RUN_SCHEMA = {
    "type": "integer",
    "minimum": 100,
    "maximum": MAX_RUN_MS,
    "default": DEFAULT_MAX_RUN_MS,
}
_ROUTE_CELL_SCHEMA = {
    "type": "string",
    "pattern": r"^[A-Wa-w](0[1-9]|[12][0-9]|3[0-3])$",
}
_OVERRIDE_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "objective": {"type": "string", "maxLength": 64},
        "route": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": _ROUTE_CELL_SCHEMA,
        },
        "engagement_policy": {
            "type": "string",
            "enum": [
                "engage_if_visible",
                "avoid_until_target",
                "hold_fire",
                "force_fight",
            ],
        },
        "reasoning": {"type": "string", "maxLength": 160},
        "plan_note": {"type": "string", "minLength": 1, "maxLength": 80},
    },
    "required": ["route", "plan_note"],
    "additionalProperties": False,
}


def _object_schema(
    properties: Mapping[str, Any] | None = None,
    *,
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties or {}),
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "prepare_jev_player",
        "description": (
            "Prepare one Doom Arena participant for Jev control, validate local "
            "preconditions, and return the filtered opening status."
        ),
        "inputSchema": _object_schema(
            {
                "participant_id": _PARTICIPANT_SCHEMA,
                "agent_name": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 32,
                    "pattern": r"^\S+(?:\s+\S+)?$",
                },
                "control_mode": {
                    "type": "string",
                    "enum": ["jev_only", "jev_hybrid"],
                },
            },
            required=["participant_id"],
        ),
    },
    {
        "name": "run_jev_player",
        "description": (
            "Run or join the supervised Jev controller until completion, handoff, "
            "cancellation, or a bounded return deadline."
        ),
        "inputSchema": _object_schema(
            {
                "strategic_directive": _DIRECTIVE_SCHEMA,
                "max_run_ms": _MAX_RUN_SCHEMA,
            }
        ),
    },
    {
        "name": "resume_jev_player",
        "description": (
            "Resolve a strategic handoff with a directive or validated override "
            "plan, then resume the bounded controller wait."
        ),
        "inputSchema": _object_schema(
            {
                "strategic_directive": _DIRECTIVE_SCHEMA,
                "override_plan": _OVERRIDE_PLAN_SCHEMA,
                "max_run_ms": _MAX_RUN_SCHEMA,
            }
        ),
    },
    {
        "name": "get_jev_player_status",
        "description": "Return the sanitized state of the supervised Jev controller.",
        "inputSchema": _object_schema(),
    },
    {
        "name": "stop_jev_player",
        "description": "Stop Jev control, further plan writes, and sensitive in-memory state.",
        "inputSchema": _object_schema(),
    },
)

_TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOL_DEFINITIONS}


class MCPProtocolError(ValueError):
    """A request did not match the advertised MCP contract."""


def read_exact_bytes(stream: BinaryIO, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError(
                f"Unexpected EOF while reading MCP body ({remaining} bytes missing)"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_message(stream: BinaryIO) -> tuple[dict[str, Any] | None, str | None]:
    headers: dict[str, str] = {}
    while True:
        raw_line = stream.readline()
        if raw_line == b"":
            return None, None
        if not headers and not raw_line.strip():
            continue
        if not headers and raw_line.lstrip().startswith(b"{"):
            message = json.loads(raw_line.decode("utf-8"))
            if not isinstance(message, dict):
                raise MCPProtocolError("JSON-RPC message must be an object")
            return message, "ndjson"
        line = raw_line.decode("ascii").strip()
        if not line:
            break
        name, separator, value = line.partition(":")
        if separator:
            headers[name.lower()] = value.strip()

    length_text = headers.get("content-length")
    if length_text is None:
        raise MCPProtocolError("Missing Content-Length header")
    try:
        length = int(length_text)
    except ValueError as exc:
        raise MCPProtocolError("Invalid Content-Length header") from exc
    if length < 0:
        raise MCPProtocolError("Invalid Content-Length header")
    body = read_exact_bytes(stream, length)
    message = json.loads(body.decode("utf-8"))
    if not isinstance(message, dict):
        raise MCPProtocolError("JSON-RPC message must be an object")
    return message, "content-length"


def read_message(stream: BinaryIO | None = None) -> dict[str, Any] | None:
    """Read one JSON-RPC message, retaining framing for ``write_message``."""

    global MCP_OUTPUT_FRAMING
    source = stream or sys.stdin.buffer
    message, framing = _read_message(source)
    if framing is not None:
        MCP_OUTPUT_FRAMING = framing
    return message


def _write_message(stream: BinaryIO, message: Mapping[str, Any], framing: str) -> None:
    body = json.dumps(
        message,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if framing == "ndjson":
        stream.write(body + b"\n")
    else:
        stream.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n")
        stream.write(body)
    stream.flush()


def write_message(
    message: Mapping[str, Any],
    stream: BinaryIO | None = None,
) -> None:
    """Write one JSON-RPC message using the most recently detected framing."""

    _write_message(stream or sys.stdout.buffer, message, MCP_OUTPUT_FRAMING)


class StdioTransport:
    """Small framing adapter whose state is isolated per MCP process/test."""

    def __init__(self, input_stream: BinaryIO, output_stream: BinaryIO) -> None:
        self.input_stream = input_stream
        self.output_stream = output_stream
        self.output_framing = "content-length"
        self._write_lock = threading.Lock()

    def read_message(self) -> dict[str, Any] | None:
        message, framing = _read_message(self.input_stream)
        if framing is not None:
            self.output_framing = framing
        return message

    def write_message(self, message: Mapping[str, Any]) -> None:
        with self._write_lock:
            _write_message(self.output_stream, message, self.output_framing)


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "arguments") -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, Mapping):
            raise MCPProtocolError(f"{path} must be an object")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise MCPProtocolError(f"{path} is missing required field(s): {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value).difference(properties))
            if unknown:
                raise MCPProtocolError(
                    f"{path} has unexpected field(s): {', '.join(str(item) for item in unknown)}"
                )
        for name, child in value.items():
            if name in properties:
                _validate_schema(child, properties[name], f"{path}.{name}")
        return
    if expected_type == "array":
        if not isinstance(value, list):
            raise MCPProtocolError(f"{path} must be an array")
        if len(value) < int(schema.get("minItems", 0)):
            raise MCPProtocolError(f"{path} contains too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise MCPProtocolError(f"{path} contains too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]")
        return
    if expected_type == "string":
        if not isinstance(value, str):
            raise MCPProtocolError(f"{path} must be a string")
        if len(value) < int(schema.get("minLength", 0)):
            raise MCPProtocolError(f"{path} is too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise MCPProtocolError(f"{path} is too long")
        if "enum" in schema and value not in schema["enum"]:
            raise MCPProtocolError(f"{path} must be one of {schema['enum']}")
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            raise MCPProtocolError(f"{path} has an invalid format")
        return
    if expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise MCPProtocolError(f"{path} must be an integer")
        if "minimum" in schema and value < int(schema["minimum"]):
            raise MCPProtocolError(f"{path} must be at least {schema['minimum']}")
        if "maximum" in schema and value > int(schema["maximum"]):
            raise MCPProtocolError(f"{path} must be at most {schema['maximum']}")
        return
    raise MCPProtocolError(f"unsupported schema type at {path}")


def _safe_error_message(error: BaseException) -> str:
    message = " ".join(str(error).split()) or type(error).__name__
    for name in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(?:sk-or-v1-|sk-ant-|sk-proj-)[A-Za-z0-9_-]{8,}", "[REDACTED]", message)
    return message[:1_000]


def _result_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class JevDoomMCPServer:
    """JSON-RPC dispatcher around an injected Jev player controller."""

    def __init__(self, controller: Any, transport: StdioTransport) -> None:
        self.controller = controller
        self.transport = transport
        self._closed = False
        self._active_lock = threading.Lock()
        self._queued_requests: dict[tuple[type[Any], Any], str] = {}
        self._cancelled_queued_requests: set[tuple[type[Any], Any]] = set()
        self._active_request_key: tuple[type[Any], Any] | None = None
        self._active_request_id: Any = None
        self._active_tool_name = ""

    def _send_result(self, message_id: Any, result: Any) -> None:
        self.transport.write_message({"jsonrpc": "2.0", "id": message_id, "result": result})

    def _send_error(self, message_id: Any, code: int, message: str) -> None:
        self.transport.write_message(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": code, "message": message},
            }
        )

    def _send_tool_result(self, message_id: Any, value: Any, *, is_error: bool) -> None:
        self._send_result(
            message_id,
            {
                "content": [{"type": "text", "text": _result_text(value)}],
                "isError": is_error,
            },
        )

    def _stop_controller(self) -> None:
        try:
            self.controller.stop()
        except Exception:  # noqa: BLE001 - cleanup must survive controller failures.
            # Cancellation and process cleanup must remain best-effort and must
            # never corrupt stdout with a traceback.
            return

    @staticmethod
    def _request_key(request_id: Any) -> tuple[type[Any], Any] | None:
        try:
            hash(request_id)
        except TypeError:
            return None
        return type(request_id), request_id

    def register_queued_request(self, request_id: Any, tool_name: str) -> bool:
        if tool_name not in _BOUNDED_TOOL_NAMES:
            return False
        key = self._request_key(request_id)
        if key is None:
            return False
        with self._active_lock:
            self._queued_requests[key] = tool_name
            self._cancelled_queued_requests.discard(key)
        return True

    def _begin_bounded_request(self, request_id: Any, tool_name: str) -> bool:
        key = self._request_key(request_id)
        with self._active_lock:
            if key is not None:
                self._queued_requests.pop(key, None)
                if key in self._cancelled_queued_requests:
                    self._cancelled_queued_requests.discard(key)
                    return False
            self._active_request_key = key
            self._active_request_id = request_id
            self._active_tool_name = tool_name
        return True

    def _finish_bounded_request(self, request_id: Any) -> None:
        key = self._request_key(request_id)
        with self._active_lock:
            if self._active_request_key == key:
                self._active_request_key = None
                self._active_request_id = None
                self._active_tool_name = ""

    def cancel_request(self, request_id: Any) -> bool:
        key = self._request_key(request_id)
        with self._active_lock:
            should_stop = (
                self._active_tool_name in _BOUNDED_TOOL_NAMES
                and self._active_request_key == key
            )
            cancelled_queued = key is not None and key in self._queued_requests
            if cancelled_queued:
                self._cancelled_queued_requests.add(key)
        if should_stop:
            self._stop_controller()
        return should_stop or cancelled_queued

    def cancel_active_request(self) -> bool:
        with self._active_lock:
            request_id = self._active_request_id
            has_active = self._active_tool_name in _BOUNDED_TOOL_NAMES
        return self.cancel_request(request_id) if has_active else False

    def cancel_all_requests(self) -> bool:
        with self._active_lock:
            self._cancelled_queued_requests.update(self._queued_requests)
            has_queued = bool(self._queued_requests)
            should_stop = self._active_tool_name in _BOUNDED_TOOL_NAMES
        if should_stop:
            self._stop_controller()
        return should_stop or has_queued

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_controller()
        try:
            self.controller.close()
        except Exception:  # noqa: BLE001 - cleanup must survive controller failures.
            return

    def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        tool = _TOOLS_BY_NAME.get(name)
        if tool is None:
            raise MCPProtocolError(f"Unknown tool: {name}")
        _validate_schema(arguments, tool["inputSchema"])

        if name == "prepare_jev_player":
            return self.controller.prepare(
                str(arguments["participant_id"]),
                agent_name=arguments.get("agent_name"),
                control_mode=arguments.get("control_mode"),
            )
        if name == "run_jev_player":
            return self.controller.run(
                strategic_directive=str(arguments.get("strategic_directive", "")),
                max_run_ms=int(arguments.get("max_run_ms", DEFAULT_MAX_RUN_MS)),
            )
        if name == "resume_jev_player":
            return self.controller.resume(
                strategic_directive=str(arguments.get("strategic_directive", "")),
                override_plan=arguments.get("override_plan"),
                max_run_ms=int(arguments.get("max_run_ms", DEFAULT_MAX_RUN_MS)),
            )
        if name == "get_jev_player_status":
            return self.controller.status()
        if name == "stop_jev_player":
            return self.controller.stop()
        raise AssertionError(f"unhandled tool {name}")

    def handle_message(self, message: Mapping[str, Any]) -> bool:
        message_id = message.get("id")
        method = message.get("method")
        if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
            self._send_error(message_id, -32600, "Invalid Request")
            return True

        if method == "initialize":
            params = message.get("params")
            if not isinstance(params, Mapping):
                params = {}
            requested_version = str(params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION)
            protocol_version = (
                requested_version
                if requested_version in SUPPORTED_PROTOCOL_VERSIONS
                else DEFAULT_PROTOCOL_VERSION
            )
            self._send_result(
                message_id,
                {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
            return True

        if method == "notifications/initialized":
            return True
        if method == "notifications/cancelled":
            params = message.get("params")
            if isinstance(params, Mapping) and "requestId" in params:
                self.cancel_request(params.get("requestId"))
            return True
        if method == "ping":
            self._send_result(message_id, {})
            return True
        if method == "tools/list":
            self._send_result(message_id, {"tools": list(TOOL_DEFINITIONS)})
            return True
        if method == "resources/list":
            self._send_result(message_id, {"resources": []})
            return True
        if method == "prompts/list":
            self._send_result(message_id, {"prompts": []})
            return True
        if method == "tools/call":
            params = message.get("params")
            if not isinstance(params, Mapping):
                self._send_error(message_id, -32602, "Invalid tools/call params")
                return True
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, Mapping):
                self._send_error(message_id, -32602, "Invalid tools/call params")
                return True
            track_active = name in _BOUNDED_TOOL_NAMES
            if track_active and not self._begin_bounded_request(message_id, name):
                return True
            try:
                result = self._call_tool(name, arguments)
                self._send_tool_result(message_id, result, is_error=False)
            except Exception as exc:  # noqa: BLE001 - MCP tool boundary.
                self._send_tool_result(
                    message_id,
                    {
                        "error": type(exc).__name__,
                        "message": _safe_error_message(exc),
                    },
                    is_error=True,
                )
            finally:
                if track_active:
                    self._finish_bounded_request(message_id)
            return True
        if method == "shutdown":
            self._send_result(message_id, None)
            self.close()
            return False

        if message_id is not None:
            self._send_error(message_id, -32601, f"Method not found: {method}")
        return True


def create_controller() -> Any:
    """Construct the real controller only for an actual server process."""

    from controller import JevPlayerController

    return JevPlayerController()


def serve(
    controller: Any | None = None,
    *,
    input_stream: BinaryIO | None = None,
    output_stream: BinaryIO | None = None,
) -> int:
    """Serve MCP until shutdown or EOF, always cleaning up the controller."""

    source = input_stream or sys.stdin.buffer
    sink = output_stream or sys.stdout.buffer
    active_controller = controller if controller is not None else create_controller()
    transport = StdioTransport(source, sink)
    server = JevDoomMCPServer(active_controller, transport)
    inbox: queue.Queue[tuple[str, Any]] = queue.Queue()

    def read_loop() -> None:
        while True:
            try:
                message = transport.read_message()
            except (json.JSONDecodeError, UnicodeDecodeError, MCPProtocolError, EOFError) as exc:
                inbox.put(("parse_error", exc))
                continue
            if message is None:
                server.cancel_all_requests()
                inbox.put(("eof", None))
                return
            method = message.get("method")
            if method == "notifications/cancelled":
                params = message.get("params")
                if isinstance(params, Mapping) and "requestId" in params:
                    server.cancel_request(params.get("requestId"))
                continue
            if method == "shutdown":
                server.cancel_all_requests()
            elif method == "tools/call":
                params = message.get("params")
                name = params.get("name") if isinstance(params, Mapping) else None
                if isinstance(name, str):
                    server.register_queued_request(message.get("id"), name)
            inbox.put(("message", message))

    reader = threading.Thread(
        target=read_loop,
        name="jev-doom-mcp-stdin",
        daemon=True,
    )
    reader.start()
    try:
        while True:
            kind, payload = inbox.get()
            if kind == "parse_error":
                try:
                    server._send_error(None, -32700, f"Parse error: {_safe_error_message(payload)}")
                except (BrokenPipeError, OSError):
                    break
                continue
            if kind == "eof":
                break
            try:
                should_continue = server.handle_message(payload)
            except (BrokenPipeError, OSError):
                break
            if not should_continue:
                break
    finally:
        server.close()
        reader.join(timeout=1.0)
    return 0


def main() -> int:
    try:
        return serve()
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_MAX_RUN_MS",
    "MAX_RUN_MS",
    "MCP_OUTPUT_FRAMING",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOL_DEFINITIONS",
    "JevDoomMCPServer",
    "MCPProtocolError",
    "StdioTransport",
    "create_controller",
    "read_exact_bytes",
    "read_message",
    "serve",
    "write_message",
]
