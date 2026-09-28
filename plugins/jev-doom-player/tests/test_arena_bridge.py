from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import arena_bridge


def test_resolve_repo_root_finds_source_tree():
    root = arena_bridge.resolve_repo_root()
    assert (root / "scripts" / "doom_arena_mcp.py").is_file()


def test_load_repo_env_only_reads_allowlisted_names(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=fake-key\nUNRELATED_SECRET=do-not-load\nDOOM_ARENA_BASE_URL=http://127.0.0.1:9999\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("UNRELATED_SECRET", raising=False)
    monkeypatch.delenv("DOOM_ARENA_BASE_URL", raising=False)

    loaded = arena_bridge.load_repo_env(tmp_path)

    assert loaded == {"OPENROUTER_API_KEY", "DOOM_ARENA_BASE_URL"}
    assert "UNRELATED_SECRET" not in __import__("os").environ


class FakeClient:
    def __init__(self, token_payload, rows=None, run_stats=None):
        self.run_id = "run_1"
        self._payload = token_payload
        self._rows = rows or []
        self._run_stats = run_stats
        self.verified = None

    def _sync_run_metadata(self):
        pass

    def _verify_controller_token(self, participant_id, token):
        self.verified = (participant_id, token)

    def _read_participant_intent_rows(self):
        return self._rows

    def _request(self, method, path):
        assert (method, path) == ("GET", "/api/arena/run-stats")
        if self._run_stats is None:
            raise OSError("run stats unavailable")
        return json.dumps(self._run_stats)


def test_load_controller_token_is_strict(tmp_path):
    token_path = tmp_path / "tokens.json"
    token_path.write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "enforce_controller_tokens": True,
                "player_1": {"controller_token": "secret-token"},
            }
        ),
        encoding="utf-8",
    )
    arena = SimpleNamespace(CONTROLLER_TOKENS_PATH=token_path)
    client = FakeClient({})

    assert arena_bridge.load_controller_token(arena, client, "player_1") == "secret-token"
    assert client.verified == ("player_1", "secret-token")


def test_load_controller_token_rejects_stale_run(tmp_path):
    token_path = tmp_path / "tokens.json"
    token_path.write_text(
        json.dumps(
            {
                "run_id": "run_old",
                "enforce_controller_tokens": True,
                "player_1": {"controller_token": "secret-token"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(arena_bridge.ArenaBridgeError, match="different arena run"):
        arena_bridge.load_controller_token(SimpleNamespace(CONTROLLER_TOKENS_PATH=token_path), FakeClient({}), "player_1")


def test_recover_sequence_is_scoped_to_run_and_participant():
    client = FakeClient(
        {},
        rows=[
            {"run_id": "run_1", "participant_id": "player_1", "sequence_number": "4"},
            {"run_id": "run_1", "participant_id": "player_2", "sequence_number": "99"},
            {"run_id": "run_old", "participant_id": "player_1", "sequence_number": "77"},
        ],
    )
    assert arena_bridge.recover_next_sequence(client, "player_1") == 5


def test_recover_sequence_includes_expired_and_cleared_history():
    client = FakeClient(
        {},
        rows=[{"run_id": "run_1", "participant_id": "player_1", "sequence_number": "4"}],
        run_stats={
            "intent_lifecycles": [
                {"run_id": "run_1", "participant_id": "player_1", "sequence_number": 8},
                {"run_id": "run_1", "participant_id": "player_2", "sequence_number": 99},
                {"run_id": "run_old", "participant_id": "player_1", "sequence_number": 77},
            ]
        },
    )

    assert arena_bridge.recover_next_sequence(client, "player_1") == 9
