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


def test_participant_prompt_uses_automatic_session_identity():
    prompt = prompts.instructions(
        participant_id="player_1",
        model="",
        opponent_id="player_2",
        controller_token="token-123",
        enforce_tokens=True,
        control_mode="hierarchical",
    )

    assert "IDENTITY (AUTOMATIC)" in prompt
    assert "without guessing or asking the user" in prompt
    assert "reads the current session metadata" in prompt
    assert '"coding_assistant"' not in prompt
    assert '"model"' not in prompt
    assert "Never submit an MCP transport package name or version" in prompt
    assert "`agent_name` is only your creative alias" in prompt
    assert "readiness still succeeds with an explicit unavailable label" in prompt
    assert "DOOM_ARENA_CODING_ASSISTANT" in prompt
    assert "DOOM_ARENA_MODEL_IDENTITY" in prompt
    assert "do not loop on reconnects" in prompt


def test_participant_prompt_requests_doom_alias_only_for_first_match():
    first_prompt = prompts.instructions(
        participant_id="player_1",
        model="",
        opponent_id="player_2",
        controller_token="token-123",
        enforce_tokens=True,
        current_round=1,
        total_rounds=3,
        control_mode="hierarchical",
    )
    later_prompt = prompts.instructions(
        participant_id="player_1",
        model="",
        opponent_id="player_2",
        controller_token="token-123",
        enforce_tokens=True,
        current_round=2,
        total_rounds=3,
        control_mode="hierarchical",
        agent_name="Expense Goblin",
    )

    assert "ARENA NAME (FIRST MATCH ONLY)" in first_prompt
    assert "broad audience with no Doom or gaming knowledge" in first_prompt
    assert "do not copy a sample" in first_prompt
    assert "brainstorm at least five candidates" not in first_prompt
    assert "concrete ridiculous character" in first_prompt
    assert "clear mental image or tiny story" in first_prompt
    assert "Avoid bland alliteration" in first_prompt
    assert "two abstract nouns" in first_prompt
    assert "player_1 should draw from workplace chaos" in first_prompt
    assert "player_2 should draw from food" in first_prompt
    assert "name is already claimed" in first_prompt
    assert "Spreadsheet Slayer" not in first_prompt
    assert "Lunch Break Menace" not in first_prompt
    assert "Avoid obscure lore" in first_prompt
    assert "one or two words only" in first_prompt
    assert '"agent_name": "chosen alias"' in first_prompt
    assert "resubmit the exact same alias" in first_prompt
    assert "reuse the exact quoted locked name" in first_prompt
    assert "ARENA NAME (ALREADY CHOSEN)" in later_prompt
    assert "Your locked arena name is `Expense Goblin`" in later_prompt
    assert '"agent_name": "Expense Goblin"' in later_prompt


def test_participant_prompt_requires_a_battle_quip_for_every_plan():
    prompt = prompts.instructions(
        participant_id="player_1",
        model="",
        opponent_id="player_2",
        controller_token="token-123",
        enforce_tokens=True,
        control_mode="hierarchical",
    )
    plan_tool = next(tool for tool in mcp.tool_definitions() if tool["name"] == "set_participant_plan")

    assert "`plan_note` is required on every decision" in prompt
    assert "short, funny, first-person battle quip" in prompt
    assert "plan_note" in plan_tool["inputSchema"]["required"]
    assert plan_tool["inputSchema"]["properties"]["plan_note"]["maxLength"] == 80


def test_participant_prompt_makes_goal_and_reason_sentence_compatible():
    prompt = prompts.instructions(
        participant_id="player_1",
        model="",
        opponent_id="player_2",
        controller_token="token-123",
        enforce_tokens=True,
        control_mode="hierarchical",
    )

    assert "fits after `is trying to`" in prompt
    assert "fits after `because`" in prompt
    assert "Do not begin it with `because`" in prompt


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
    monkeypatch.setattr(mcp, "codex_ancestor_process_context", lambda: None)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("DOOM_ARENA_CODING_ASSISTANT", raising=False)
    monkeypatch.delenv("DOOM_ARENA_MODEL_IDENTITY", raising=False)
    client = mcp.DoomArenaClient("http://stub.invalid")
    return client


def test_set_participant_ready_uses_trusted_environment_identity(tmp_path, monkeypatch):
    client = _make_client(monkeypatch, tmp_path / "does_not_exist.json")
    client.run_id = "run_identity"
    client.scenario_id = "duel_e1m8"
    monkeypatch.setenv("DOOM_ARENA_CODING_ASSISTANT", "Doom Arena smoke test")
    monkeypatch.setenv("DOOM_ARENA_MODEL_IDENTITY", "deterministic autopilot")
    monkeypatch.setattr(client, "_verify_controller_token", lambda *_args, **_kwargs: None)
    captured = {}

    def fake_request(method, path, body=None, content_type=None):
        captured.update(json.loads(body.decode("utf-8")))
        return '{"ok": true}'

    monkeypatch.setattr(client, "_request", fake_request)

    response = json.loads(
        client.set_participant_ready(
            "player_1",
            controller_token="token",
            agent_name="Hell's Helpdesk",
        )
    )

    assert captured["agent_name"] == "Hell's Helpdesk"
    assert captured["coding_assistant"] == "Doom Arena smoke test"
    assert captured["model"] == "deterministic autopilot"
    assert captured["agent_label"] == (
        "Hell's Helpdesk, Doom Arena smoke test, deterministic autopilot"
    )
    assert captured["identity_source"] == "environment"
    assert response["agent_name"] == "Hell's Helpdesk"
    assert response["agent_label"] == (
        "Hell's Helpdesk, Doom Arena smoke test, deterministic autopilot"
    )
    assert response["identity_source"] == "environment"


def test_ready_tool_schema_exposes_alias_but_no_manual_identity_fields():
    ready_tool = next(tool for tool in mcp.tool_definitions() if tool["name"] == "set_participant_ready")

    assert ready_tool["inputSchema"]["properties"]["agent_name"]["maxLength"] == 32
    assert ready_tool["inputSchema"]["properties"]["agent_name"]["pattern"] == r"^\S+(?:\s+\S+)?$"
    assert "at most two words" in ready_tool["inputSchema"]["properties"]["agent_name"]["description"]
    assert "immediately understandable everyday wordplay" in ready_tool["inputSchema"]["properties"]["agent_name"]["description"]
    assert "concrete ridiculous character" in ready_tool["inputSchema"]["properties"]["agent_name"]["description"]
    assert "not bland alliteration" in ready_tool["inputSchema"]["properties"]["agent_name"]["description"]
    assert "unique within the duel" in ready_tool["inputSchema"]["properties"]["agent_name"]["description"]
    assert "without Doom or gaming knowledge" in ready_tool["description"]
    assert "duplicate-name rejection" in ready_tool["description"]
    assert "coding_assistant" not in ready_tool["inputSchema"]["properties"]
    assert "model" not in ready_tool["inputSchema"]["properties"]
    assert set(ready_tool["inputSchema"]["required"]) == {"participant_id", "agent_name"}


def test_set_participant_ready_detects_codex_session_identity(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "07" / "30"
    sessions_dir.mkdir(parents=True)
    thread_id = "019fb38c-6f2c-7960-834e-025b687b341e"
    rollout_path = sessions_dir / f"rollout-2026-07-30T11-02-33-{thread_id}.jsonl"
    rollout_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": thread_id,
                            "thread_settings": {
                                "model": "gpt-5.6-sol",
                                "reasoning_effort": "low",
                                "service_tier": "priority",
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {
                            "model": "gpt-5.6-sol",
                            "effort": "low",
                            "thread_settings": {
                                "model": "gpt-5.6-sol",
                                "reasoning_effort": "low",
                                "service_tier": "priority",
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client = _make_client(monkeypatch, tmp_path / "does_not_exist.json")
    client.run_id = "run_identity"
    client.scenario_id = "duel_e1m8"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", thread_id)
    monkeypatch.setattr(client, "_verify_controller_token", lambda *_args, **_kwargs: None)
    captured = {}

    def fake_request(method, path, body=None, content_type=None):
        captured.update(json.loads(body.decode("utf-8")))
        return '{"ok": true}'

    monkeypatch.setattr(client, "_request", fake_request)

    response = json.loads(
        client.set_participant_ready(
            "player_1",
            controller_token="token",
            agent_name="Expense Goblin",
        )
    )

    assert captured["agent_name"] == "Expense Goblin"
    assert captured["coding_assistant"] == "Codex"
    assert captured["model"] == "gpt-5.6-sol low fast"
    assert captured["identity_source"] == "codex_session"
    assert response["agent_label"] == (
        "Expense Goblin, Codex, gpt-5.6-sol low fast"
    )
    assert response["identity_source"] == "codex_session"


def test_set_participant_ready_detects_codex_identity_from_parent_process(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "07" / "30"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / (
        "rollout-2026-07-30T19-07-56-"
        "019fb46d-1a10-7723-b393-41846d3a1cb7.jsonl"
    )
    controller_cwd = str(tmp_path / "controller")
    rollout_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "cwd": controller_cwd,
                            "thread_settings": {
                                "model": "gpt-5.6-sol",
                                "reasoning_effort": "low",
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {
                            "model": "gpt-5.6-sol",
                            "effort": "low",
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rollout_started = mcp.codex_rollout_started_at(rollout_path)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setattr(
        mcp,
        "codex_ancestor_process_context",
        lambda: {
            "pid": 123,
            "cwd": controller_cwd,
            "started_at": rollout_started,
            "open_rollouts": [],
        },
    )
    monkeypatch.setattr(mcp, "process_file_open_pids", lambda _path: {123})

    assert mcp.detect_codex_session_identity() == ("Codex", "gpt-5.6-sol low")


def test_parent_process_identity_fallback_rejects_ambiguous_rollout(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "07" / "30"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / (
        "rollout-2026-07-30T19-07-56-"
        "019fb46d-1a10-7723-b393-41846d3a1cb7.jsonl"
    )
    rollout_path.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {
                    "cwd": str(tmp_path / "different-controller"),
                    "thread_settings": {
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "low",
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setattr(
        mcp,
        "codex_ancestor_process_context",
        lambda: {
            "pid": 123,
            "cwd": str(tmp_path / "controller"),
            "started_at": mcp.codex_rollout_started_at(rollout_path),
            "open_rollouts": [],
        },
    )

    assert mcp.detect_codex_session_identity() is None


def test_parent_process_identity_fallback_refuses_multiple_owned_candidates(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "07" / "30"
    sessions_dir.mkdir(parents=True)
    controller_cwd = str(tmp_path / "controller")
    rollout_paths = [
        sessions_dir / "rollout-2026-07-30T19-07-56-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.jsonl",
        sessions_dir / "rollout-2026-07-30T19-07-57-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.jsonl",
    ]
    for index, rollout_path in enumerate(rollout_paths):
        rollout_path.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "cwd": controller_cwd,
                        "thread_settings": {
                            "model": f"gpt-test-{index}",
                            "reasoning_effort": "low",
                        },
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setattr(
        mcp,
        "codex_ancestor_process_context",
        lambda: {
            "pid": 123,
            "cwd": controller_cwd,
            "started_at": mcp.codex_rollout_started_at(rollout_paths[0]),
            "open_rollouts": [],
        },
    )
    monkeypatch.setattr(mcp, "process_file_open_pids", lambda _path: {123})

    assert mcp.detect_codex_session_identity() is None


@pytest.mark.parametrize(
    ("open_pids", "expected"),
    [
        (set(), None),
        ({123}, ("Codex", "gpt-5.6-sol low fast")),
    ],
)
def test_parent_process_identity_fallback_requires_owned_resumed_session(
    tmp_path,
    monkeypatch,
    open_pids,
    expected,
):
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "07" / "30"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / (
        "rollout-2026-07-30T15-07-56-"
        "019fb46d-1a10-7723-b393-41846d3a1cb7.jsonl"
    )
    controller_cwd = str(tmp_path / "controller")
    rollout_path.write_text(
        json.dumps(
            {
                "type": "turn_context",
                "payload": {
                    "model": "gpt-5.6-sol",
                    "effort": "low",
                    "thread_settings": {"service_tier": "priority"},
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "session_meta",
                "payload": {"cwd": controller_cwd},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setattr(
        mcp,
        "codex_ancestor_process_context",
        lambda: {
            "pid": 123,
            "cwd": controller_cwd,
            "started_at": (mcp.codex_rollout_started_at(rollout_path) or 0) + 600,
            "open_rollouts": [],
        },
    )
    monkeypatch.setattr(mcp, "process_file_open_pids", lambda _path: open_pids)

    assert mcp.detect_codex_session_identity() == expected


def test_set_participant_ready_degrades_without_using_transport_metadata(tmp_path, monkeypatch):
    client = _make_client(monkeypatch, tmp_path / "does_not_exist.json")
    client.note_client_initialized(
        {"clientInfo": {"name": "codex-mcp-client", "version": "0.145.0"}}
    )
    monkeypatch.setattr(client, "_verify_controller_token", lambda *_args, **_kwargs: None)
    captured = {}

    def fake_request(_method, _path, body=None, _content_type=None):
        captured.update(json.loads(body.decode("utf-8")))
        return '{"ok": true}'

    monkeypatch.setattr(client, "_request", fake_request)

    response = json.loads(
        client.set_participant_ready(
            "player_1",
            controller_token="token",
            agent_name="Budget Falcon",
        )
    )

    assert captured["coding_assistant"] == "Undetected assistant"
    assert captured["model"] == "Model unavailable"
    assert captured["identity_source"] == "unavailable"
    assert "codex-mcp-client" not in captured["agent_label"]
    assert "DOOM_ARENA_CODING_ASSISTANT" in response["identity_warning"]
    assert "DOOM_ARENA_MODEL_IDENTITY" in response["identity_warning"]


def test_set_participant_ready_requires_agent_name_before_http(tmp_path, monkeypatch):
    client = _make_client(monkeypatch, tmp_path / "does_not_exist.json")
    monkeypatch.setattr(client, "_verify_controller_token", lambda *_args, **_kwargs: None)
    request_attempted = False

    def fake_request(*_args, **_kwargs):
        nonlocal request_attempted
        request_attempted = True
        return '{"ok": true}'

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(mcp.DoomArenaError, match="agent_name"):
        client.set_participant_ready("player_1", controller_token="token")

    assert request_attempted is False


@pytest.mark.parametrize(
    ("coding_assistant", "model", "message"),
    [
        ("", "gpt-5.6-sol low fast", "coding_assistant"),
        ("Coding assistant", "gpt-5.6-sol low fast", "coding_assistant"),
        ("Codex", "", "model"),
        ("codex-mcp-client", "0.145.0", "transport"),
        ("Codex", "<model from client>", "placeholder"),
    ],
)
def test_validate_agent_identity_rejects_invalid_identity(coding_assistant, model, message):
    with pytest.raises(mcp.DoomArenaError, match=message):
        mcp.validate_agent_identity(coding_assistant, model)


@pytest.mark.parametrize("agent_name", ["", "x", "Player 1", "comma, fiend", "Three Word Menace"])
def test_validate_agent_name_rejects_generic_or_invalid_names(agent_name):
    with pytest.raises(mcp.DoomArenaError):
        mcp.validate_agent_name(agent_name)


def test_format_agent_identity_label_uses_alias_assistant_model_order():
    assert mcp.format_agent_identity_label(
        "Codex",
        "gpt-5.6-sol low fast",
        "Expense Goblin",
    ) == "Expense Goblin, Codex, gpt-5.6-sol low fast"


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
