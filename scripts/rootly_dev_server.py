#!/usr/bin/env python3
"""Local Doom WASM dev server with a Rootly ingest endpoint.

The browser calls /api/rootly/last-week. This process reads ROOTLY_API_TOKEN,
calls Rootly server-side, writes src/rootly_incidents.local.tsv, then the
browser can load that TSV without ever seeing the token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fetch_rootly_incidents


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
LOCAL_TSV = SRC_DIR / "rootly_incidents.local.tsv"
AGENTIC_STATE_TSV = SRC_DIR / "agentic_game_state.local.tsv"
AGENTIC_COMMAND_TSV = SRC_DIR / "agentic_monster_commands.local.tsv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve Doom WASM and fetch last week's Rootly incidents locally."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--time-field", default="created_at")
    parser.add_argument("--max-incidents", type=int, default=24)
    return parser.parse_args()


class RootlyDevServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[SimpleHTTPRequestHandler],
        args: argparse.Namespace,
    ):
        super().__init__(server_address, handler_class)
        self.args = args


class RootlyDevHandler(SimpleHTTPRequestHandler):
    server: RootlyDevServer

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(SRC_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]

        if path == "/api/rootly/last-week":
            self.fetch_last_week()
            return

        if path == "/api/agentic/state":
            self.write_agentic_state()
            return

        if path == "/api/agentic/commands":
            self.write_agentic_commands()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]

        if path == "/api/rootly/last-week":
            self.fetch_last_week()
            return

        if path == "/api/agentic/state":
            self.read_agentic_state()
            return

        if path == "/api/agentic/commands":
            self.read_agentic_commands()
            return

        super().do_GET()

    def write_agentic_state(self) -> None:
        length_header = self.headers.get("Content-Length")
        length = int(length_header or "0")
        body = self.rfile.read(length)

        AGENTIC_STATE_TSV.write_bytes(body)
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": "agentic_game_state.local.tsv",
                "bytes": len(body),
            },
        )

    def read_agentic_state(self) -> None:
        if not AGENTIC_STATE_TSV.exists():
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "agentic_game_state.local.tsv has not been written yet.",
                },
            )
            return

        body = AGENTIC_STATE_TSV.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_agentic_commands(self) -> None:
        length_header = self.headers.get("Content-Length")
        length = int(length_header or "0")
        body = self.rfile.read(length)

        AGENTIC_COMMAND_TSV.write_bytes(body)
        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": "agentic_monster_commands.local.tsv",
                "bytes": len(body),
            },
        )

    def read_agentic_commands(self) -> None:
        if not AGENTIC_COMMAND_TSV.exists():
            self.write_json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "agentic_monster_commands.local.tsv has not been written yet.",
                },
            )
            return

        body = AGENTIC_COMMAND_TSV.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def fetch_last_week(self) -> None:
        token = os.environ.get("ROOTLY_API_TOKEN")
        if not token:
            self.write_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "ROOTLY_API_TOKEN is not set in the dev server environment.",
                },
            )
            return

        args = SimpleNamespace(
            lookback_days=self.server.args.lookback_days,
            time_field=self.server.args.time_field,
            max_incidents=self.server.args.max_incidents,
            output=str(LOCAL_TSV),
        )

        try:
            incidents = fetch_rootly_incidents.fetch_incidents(args, token)
            fetch_rootly_incidents.write_tsv(LOCAL_TSV, incidents)
        except RuntimeError as exc:
            self.write_json(
                HTTPStatus.BAD_GATEWAY,
                {
                    "ok": False,
                    "error": str(exc),
                },
            )
            return

        self.write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "count": len(incidents),
                "path": "rootly_incidents.local.tsv",
            },
        )

    def write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        message = format % args
        token = os.environ.get("ROOTLY_API_TOKEN", "")
        if token:
            message = message.replace(token, "[redacted]")
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), message)
        )


def main() -> int:
    args = parse_args()
    server = RootlyDevServer((args.host, args.port), RootlyDevHandler, args)
    url = f"http://{args.host}:{args.port}/"

    print(f"Serving Doom WASM from {SRC_DIR}")
    print(f"Open {url}")
    print("Rootly endpoint: /api/rootly/last-week")
    print("ROOTLY_API_TOKEN is read server-side only and is never sent to the browser.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
