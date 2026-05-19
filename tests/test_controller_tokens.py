"""Tests for the controller-token control path.

These cover the exact failure modes that bit us debugging the duel on macOS:
stale token files, wrong tokens, missing participants. The token verification
logic is the layer between MCP agents and the arena server, and it is the
most likely thing to silently break when extending the duel surface.
"""

import json
from pathlib import Path

import pytest

import doom_arena_duel_prompts as prompts
import doom_arena_mcp as mcp


# --------------------------------------------------------------------------- #
# build_controller_tokens
# --------------------------------------------------------------------------- #

def test_build_controller_tokens_has_expected_shape():
    tokens = prompts.build_controller_tokens(
        run_id="run_abc",
        player_1_model="codex",
        player_2_model="claude",
        enforce=True,
    )
    assert tokens["run_id"] == "run_abc"
    assert tokens["enforce_controller_tokens"] is True
    assert tokens["player_1"]["model"] == "codex"
    assert tokens["player_2"]["model"] == "claude"
    assert tokens["player_1"]["controller_token"]
    assert tokens["player_2"]["controller_token"]


def test_build_controller_tokens_generates_distinct_tokens():
    tokens = prompts.build_controller_tokens("run_x", "a", "b", True)
    assert tokens["player_1"]["controller_token"] != tokens["player_2"]["controller_token"]


def test_build_controller_tokens_passes_enforce_flag_through():
    tokens = prompts.build_controller_tokens("run_x", "a", "b", False)
    assert tokens["enforce_controller_tokens"] is False


# --------------------------------------------------------------------------- #
# write_controller_tokens
# --------------------------------------------------------------------------- #

def test_write_controller_tokens_writes_both_paths(tmp_path, monkeypatch):
    run_dir = tmp_path / "run_dir"
    run_dir.mkdir()
    host_path = tmp_path / "arena_controller_tokens.local.json"
    monkeypatch.setattr(prompts, "CONTROLLER_TOKENS_PATH", host_path)

    tokens = prompts.build_controller_tokens("run_xyz", "a", "b", True)
    prompts.write_controller_tokens(run_dir, tokens)

    on_run_dir = json.loads((run_dir / "controller_tokens.json").read_text())
    on_host = json.loads(host_path.read_text())
    assert on_run_dir == tokens
    assert on_host == tokens


# --------------------------------------------------------------------------- #
# DoomArenaClient._controller_tokens (loader)
# --------------------------------------------------------------------------- #

def _make_client(monkeypatch, host_path: Path) -> mcp.DoomArenaClient:
    monkeypatch.setattr(mcp, "CONTROLLER_TOKENS_PATH", host_path)
    client = mcp.DoomArenaClient("http://stub.invalid")
    return client


def test_controller_tokens_returns_disabled_when_file_missing(tmp_path, monkeypatch):
    client = _make_client(monkeypatch, tmp_path / "does_not_exist.json")
    assert client._controller_tokens() == {"enforce_controller_tokens": False}


def test_controller_tokens_raises_on_malformed_json(tmp_path, monkeypatch):
    host_path = tmp_path / "tokens.json"
    host_path.write_text("not json at all{")
    client = _make_client(monkeypatch, host_path)
    with pytest.raises(mcp.DoomArenaError, match="Invalid controller token file"):
        client._controller_tokens()


def test_controller_tokens_raises_on_non_dict_payload(tmp_path, monkeypatch):
    host_path = tmp_path / "tokens.json"
    host_path.write_text("[1, 2, 3]")
    client = _make_client(monkeypatch, host_path)
    with pytest.raises(mcp.DoomArenaError, match="Invalid controller token file"):
        client._controller_tokens()


# --------------------------------------------------------------------------- #
# DoomArenaClient._verify_controller_token (the exact bug we hit)
# --------------------------------------------------------------------------- #

def _client_with_tokens(tmp_path, monkeypatch, tokens, run_id="run_current"):
    host_path = tmp_path / "tokens.json"
    host_path.write_text(json.dumps(tokens))
    client = _make_client(monkeypatch, host_path)
    # Bypass live server lookup; pretend client already knows the current run.
    monkeypatch.setattr(client, "_sync_run_metadata", lambda: None)
    client.run_id = run_id
    return client


def test_verify_controller_token_passes_when_enforcement_disabled(tmp_path, monkeypatch):
    client = _client_with_tokens(
        tmp_path, monkeypatch,
        {"enforce_controller_tokens": False},
    )
    # Should NOT raise regardless of token argument.
    client._verify_controller_token("player_1", None)
    client._verify_controller_token("player_1", "wrong")


def test_verify_controller_token_rejects_stale_run_id(tmp_path, monkeypatch):
    """The exact bug that wasted hours: token file references an old run_id."""
    tokens = {
        "run_id": "run_OLD",
        "player_1": {"model": "codex", "controller_token": "good-token"},
        "enforce_controller_tokens": True,
    }
    client = _client_with_tokens(tmp_path, monkeypatch, tokens, run_id="run_NEW")
    with pytest.raises(mcp.DoomArenaError, match="run_id run_OLD"):
        client._verify_controller_token("player_1", "good-token")


def test_verify_controller_token_rejects_unknown_participant(tmp_path, monkeypatch):
    tokens = {
        "run_id": "run_current",
        "player_1": {"model": "codex", "controller_token": "good-token"},
        "enforce_controller_tokens": True,
    }
    client = _client_with_tokens(tmp_path, monkeypatch, tokens)
    with pytest.raises(mcp.DoomArenaError, match="No controller token configured for player_2"):
        client._verify_controller_token("player_2", "anything")


def test_verify_controller_token_requires_token_when_enforcing(tmp_path, monkeypatch):
    tokens = {
        "run_id": "run_current",
        "player_1": {"model": "codex", "controller_token": "good-token"},
        "enforce_controller_tokens": True,
    }
    client = _client_with_tokens(tmp_path, monkeypatch, tokens)
    with pytest.raises(mcp.DoomArenaError, match="controller_token is required for player_1"):
        client._verify_controller_token("player_1", None)


def test_verify_controller_token_rejects_wrong_token(tmp_path, monkeypatch):
    tokens = {
        "run_id": "run_current",
        "player_1": {"model": "codex", "controller_token": "good-token"},
        "enforce_controller_tokens": True,
    }
    client = _client_with_tokens(tmp_path, monkeypatch, tokens)
    with pytest.raises(mcp.DoomArenaError, match="Invalid controller_token for player_1"):
        client._verify_controller_token("player_1", "wrong-token")


def test_verify_controller_token_accepts_correct_token(tmp_path, monkeypatch):
    tokens = {
        "run_id": "run_current",
        "player_1": {"model": "codex", "controller_token": "good-token"},
        "enforce_controller_tokens": True,
    }
    client = _client_with_tokens(tmp_path, monkeypatch, tokens)
    client._verify_controller_token("player_1", "good-token")  # no exception
