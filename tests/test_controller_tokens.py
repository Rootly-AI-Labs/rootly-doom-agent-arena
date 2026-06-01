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


def test_wait_for_match_start_does_not_false_positive_when_opening_intent_already_armed(tmp_path, monkeypatch):
    tokens = {
        "run_id": "run_current",
        "player_1": {"model": "codex", "controller_token": "good-token"},
        "enforce_controller_tokens": True,
    }
    client = _client_with_tokens(tmp_path, monkeypatch, tokens, run_id="run_current")
    client.scenario_id = "duel_e1m8"
    clock = iter((10_000, 10_001, 10_002, 10_250))
    monkeypatch.setattr(mcp, "now_ms", lambda: next(clock, 10_250))

    state_tsv = (
        "run_id\tscenario_id\ttick\tkind\tentity_id\tteam\ttype\tlabel\tx\ty\tangle\thealth\talive\tdistance_to_player\trelative_angle_to_player\tline_of_sight\tcurrent_command\tready_weapon\tammo_bullets\tammo_shells\tammo_cells\tammo_rockets\tlast_x\tlast_y\tposition_delta\tstuck_ticks\tcommand_status\tlast_action\tmode\tphase\twinner\tterminal_reason\telapsed_time_seconds\ttimeout_seconds\tmodel\tdamage_dealt\tshots_fired\tshots_hit\tinvalid_actions\tround\tseed\tintent\tintent_status\tintent_id\tintent_style\tautopilot_action\tautopilot_reason\taim_error\tpreferred_distance\tstuck_recovery\tcontroller_mode\tstrafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\tissued_at_ms\texpires_at_ms\treplan_recommended\treplan_reasons\taim_tolerance\tfire_burst_ms\tmin_fire_alignment\tmin_distance\tmax_distance\tretreat_if_closer_than\tpush_if_farther_than\tlos_lost_action\tstuck_recovery_strategy\tmovement_primitive\tturn_policy\tnavigation_target\tfire_mode\texecuted_los_lost_action\texecuted_stuck_recovery_strategy\texecuted_movement_primitive\texecuted_turn_policy\texecuted_navigation_target\texecuted_fire_mode\n"
        "run_current\tduel_e1m8\t1\tmatch\t\t\t\t\t0\t0\t0\t0\t0\t0\t0\t0\t\t\t0\t0\t0\t0\t0\t0\t0\t0\t\t\tduel\twaiting_for_agents\t\t\t0.0\t120\t\t0\t0\t0\t0\t1\t42\t\t\t\t\t\t\t0\t0\t0\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        "run_current\tduel_e1m8\t1\tparticipant\tplayer_1\tparticipant\tplayer\tplayer_1\t-206\t2142\t45\t150\t1\t2214\t26\t1\tnoop\tpistol\t200\t0\t0\t0\t-206\t2142\t0\t0\tmissing\tnoop\tduel\twaiting_for_agents\t\t\t0.0\t120\tcodex\t0\t0\t0\t0\t1\t42\tnone\tinactive\t\t\tnone\twaiting_for_both_agents\t0\t0\t0\tlow_level_command\tauto\tdirect\tonly_when_aligned\tmaintain\t\t-1\t0\t0\t0\t0\t\t0\t0\t0\t0\t0\t0\t0\tsweep\tdefault\t\tauto\topponent\tauto\t\t\t\t\t\t\n"
    )
    intent_tsv = (
        "run_id\tscenario_id\tintent_id\tissued_at_ms\texpires_at_ms\tparticipant_id\tintent\tstyle\ttarget_id\tpreferred_distance\taggression\tduration_ms\tstrafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\taim_tolerance\tfire_burst_ms\tmin_fire_alignment\tmin_distance\tmax_distance\tretreat_if_closer_than\tpush_if_farther_than\tlos_lost_action\tstuck_recovery_strategy\tmovement_primitive\tturn_policy\tnavigation_target\tfire_mode\n"
        "run_current\tduel_e1m8\tplayer_1_intent_1\t9000\t69000\tplayer_1\tengage_opponent\tbalanced\tplayer_2\t600\t0.500\t60000\talternate\tdirect\tonly_when_aligned\tclose\tlost_los,stuck,target_close\t1\t\t\t\t8\t256\t900\t192\t1200\tadvance_last_seen\tstrafe_out\t\tturn_to_enemy\topponent\tfire_when_aligned\n"
    )
    ready_tsv = "run_id\tscenario_id\tparticipant_id\tready_at_ms\tstatus\n"

    def fake_request(method: str, path: str, body=None, content_type=None):
        if method == "GET" and path == "/api/arena/reset":
            return json.dumps(
                {
                    "run_id": "run_current",
                    "scenario_id": "duel_e1m8",
                    "control_mode": "hierarchical",
                }
            )
        if method == "GET" and path == "/api/arena/state":
            return state_tsv
        if method == "GET" and path == "/api/arena/participant-intents":
            return intent_tsv
        if method == "GET" and path == "/api/arena/participant-ready":
            return ready_tsv
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(client, "_request", fake_request)
    result = json.loads(client.wait_for_match_start("player_1", controller_token="good-token", timeout_ms=100, poll_ms=50))
    assert result["started"] is False
    assert result["phase"] == "waiting_for_agents"
    assert "needs_opening_intent" not in result
    assert result["intent_participants"] == ["player_1"]
    assert result["missing_ready_participants"] == ["player_1", "player_2"]
    assert result["missing_opening_intent_participants"] == ["player_2"]
