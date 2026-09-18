"""Sanitized JSONL telemetry for Jev decisions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


PLUGIN_VERSION = "0.1.0"
_SENSITIVE_KEY = re.compile(r"(?:authorization|api[_-]?key|controller[_-]?token|secret|password)", re.I)
_SECRET_VALUE = re.compile(r"(?:sk-or-v1-|sk-ant-|sk-proj-)[A-Za-z0-9_-]{8,}")
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/(?:home|Users|root|tmp)/)")


def filtered_state_hash(state: Mapping[str, Any]) -> str:
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sanitize(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(child_key): sanitize(child, key=str(child_key)) for child_key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value[:255]]
    if isinstance(value, str):
        if _SECRET_VALUE.search(value) or _ABSOLUTE_PATH.match(value):
            return "[redacted]"
        return value[:1000]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:200]


class JsonlTelemetry:
    def __init__(self, path: str | Path | None = None):
        configured = str(path or os.environ.get("JEV_DOOM_TELEMETRY_PATH", "")).strip()
        self.path = Path(configured).expanduser() if configured else None
        self._lock = threading.Lock()

    def record(self, event: str, payload: Mapping[str, Any]) -> None:
        if self.path is None:
            return
        record = {
            "timestamp_ms": int(time.time() * 1000),
            "event": str(event)[:64],
            "plugin_version": PLUGIN_VERSION,
            **sanitize(payload),
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()

