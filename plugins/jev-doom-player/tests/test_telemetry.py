from __future__ import annotations

import json

from telemetry import JsonlTelemetry, filtered_state_hash, sanitize


def test_filtered_state_hash_is_stable_across_key_order():
    assert filtered_state_hash({"b": 2, "a": 1}) == filtered_state_hash({"a": 1, "b": 2})


def test_sanitize_redacts_secrets_and_absolute_paths():
    value = sanitize(
        {
            "controller_token": "top-secret",
            "note": "sk-or-v1-abcdefghijklmnop",
            "source": r"C:\\Users\\person\\repo",
            "ok": "safe",
        }
    )
    assert value == {
        "controller_token": "[redacted]",
        "note": "[redacted]",
        "source": "[redacted]",
        "ok": "safe",
    }


def test_jsonl_telemetry_appends_sanitized_record(tmp_path):
    path = tmp_path / "trace.jsonl"
    telemetry = JsonlTelemetry(path)
    telemetry.record("decision", {"run_id": "run_1", "api_key": "nope", "selected": "hold"})

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["event"] == "decision"
    assert record["api_key"] == "[redacted]"
    assert record["selected"] == "hold"

