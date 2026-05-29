"""Regression tests for the rationale/token-tracking/spawn/scenario improvements.

These cover the new server-side surface introduced after the baseline 32%-failure
investigation; they do not exercise the C engine (which requires a WASM rebuild).
"""

import json
import threading
from types import SimpleNamespace

import doom_arena_server as server


def make_handler_with_state(
    run_id: str = "run_test",
    scenario_id: str = "duel_e1m8",
    randomize_spawns: bool = False,
    scenario_pool=None
):
    handler = server.DoomArenaHandler.__new__(server.DoomArenaHandler)
    handler.server = SimpleNamespace(
        run_id=run_id,
        scenario_id=scenario_id,
        stats_lock=threading.Lock(),
        latest_intent_by_participant={},
        mcp_calls=[],
        active_mcp_calls={},
        mcp_call_counter=0,
        participant_ready_agents={},
        intent_records=[],
        run_results_dirs={},
        current_run_results_dir=None,
        rationale_count=0,
        token_usage={},
        duel_session_id="",
        duel_total_rounds=1,
        duel_current_round=0,
        duel_controller_tokens={},
        duel_player_1_prompt="",
        duel_player_2_prompt="",
        hide_enemy_position=False,
        duel_randomize_spawns=randomize_spawns,
        duel_scenario_pool=list(scenario_pool or []),
        duel_scenario_history=[],
        enable_cross_round_recap=False,
        recap_window=2,
        enable_map_blueprint=False,
        enable_weapon_pickups=False,
        mirror_pair=False,
        control_mode="hierarchical",
    )
    return handler


# ---------- Rationale field ----------


def test_extract_rationale_record_returns_none_when_no_rationale():
    handler = make_handler_with_state()
    record = handler.extract_rationale_record(
        {"participant_id": "player_1", "intent": "engage_opponent"},
        {"participant_id": "player_1", "intent": "engage_opponent"},
    )
    assert record is None


def test_extract_rationale_record_returns_record_when_present():
    handler = make_handler_with_state(run_id="run_xyz", scenario_id="duel_e1m8")
    raw = {
        "participant_id": "player_1",
        "intent": "engage_opponent",
        "rationale": "  Close the gap while opponent is reloading  ",
    }
    normalized = {
        "run_id": "run_xyz",
        "scenario_id": "duel_e1m8",
        "intent_id": "player_1_intent_123",
        "participant_id": "player_1",
        "intent": "engage_opponent",
        "style": "balanced",
        "sequence_number": "5",
    }
    record = handler.extract_rationale_record(raw, normalized)
    assert record is not None
    assert record["rationale"] == "Close the gap while opponent is reloading"
    assert record["intent_id"] == "player_1_intent_123"
    assert record["participant_id"] == "player_1"
    assert record["intent"] == "engage_opponent"
    assert record["sequence_number"] == "5"


def test_extract_rationale_record_truncates_long_rationale():
    handler = make_handler_with_state()
    record = handler.extract_rationale_record(
        {"rationale": "x" * 5000},
        {"participant_id": "player_1", "intent": "hold"},
    )
    assert record is not None
    assert len(record["rationale"]) == 1024


def test_append_rationale_records_writes_jsonl(tmp_path, monkeypatch):
    handler = make_handler_with_state()
    run_dir = tmp_path / "run_results"
    monkeypatch.setattr(handler, "run_dir", lambda *a, **kw: run_dir)

    records = [
        {"intent_id": "i1", "rationale": "first"},
        {"intent_id": "i2", "rationale": "second"},
    ]
    handler.append_rationale_records(records)

    written = (run_dir / "rationales.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(written) == 2
    decoded = [json.loads(line) for line in written]
    assert decoded[0]["intent_id"] == "i1"
    assert decoded[1]["rationale"] == "second"
    assert handler.server.rationale_count == 2


# ---------- Token usage tracking ----------


def test_record_token_chars_updates_per_participant_bucket():
    handler = make_handler_with_state()
    handler.record_token_chars_locked("player_1", 400, 0)
    handler.record_token_chars_locked("player_1", 0, 200)
    handler.record_token_chars_locked("player_2", 800, 1200)

    p1 = handler.server.token_usage["player_1"]
    p2 = handler.server.token_usage["player_2"]
    assert p1["request_chars"] == 400
    assert p1["response_chars"] == 200
    assert p1["request_tokens_estimated"] == 100  # 400 / 4
    assert p1["response_tokens_estimated"] == 50
    assert p1["total_tokens_estimated"] == 150
    # tool_calls counter only increments on request (start_mcp_tool_call)
    assert p1["tool_calls"] == 1

    assert p2["request_tokens_estimated"] == 200
    assert p2["response_tokens_estimated"] == 300
    assert p2["total_tokens_estimated"] == 500


# ---------- Scenario pool / spawn randomization ----------


def test_resolve_duel_scenario_pool_default_single_scenario():
    handler = make_handler_with_state()
    pool = handler.resolve_duel_scenario_pool(
        {"scenario_id": "duel_e1m8_blind_spawn"}
    )
    assert pool == ["duel_e1m8_blind_spawn"]


def test_resolve_duel_scenario_pool_with_randomize_spawns():
    handler = make_handler_with_state()
    pool = handler.resolve_duel_scenario_pool({"randomize_spawns": True})
    assert pool == ["duel_e1m8", "duel_e1m8_blind_spawn"]


def test_resolve_duel_scenario_pool_with_rotate_all_maps_only_includes_buildable():
    handler = make_handler_with_state()
    pool = handler.resolve_duel_scenario_pool({"rotate_all_maps": True})
    # Should only include scenarios that don't require a WASM rebuild
    assert "duel_e1m8" in pool
    assert "duel_e1m8_blind_spawn" in pool
    for scenario_id in pool:
        entry = next(e for e in server.DUEL_SCENARIOS if e["scenario_id"] == scenario_id)
        assert entry["requires_wasm_rebuild"] is False


def test_resolve_duel_scenario_pool_with_explicit_pool_filters_unknown():
    handler = make_handler_with_state()
    pool = handler.resolve_duel_scenario_pool(
        {"scenario_pool": ["duel_e1m8", "totally_made_up_scenario"]}
    )
    assert pool == ["duel_e1m8"]


def test_pick_round_scenario_id_rotates_when_not_randomized():
    handler = make_handler_with_state(
        randomize_spawns=False,
        scenario_pool=["duel_e1m8", "duel_e1m8_blind_spawn"],
    )
    assert handler.pick_round_scenario_id(1, {}) == "duel_e1m8"
    assert handler.pick_round_scenario_id(2, {}) == "duel_e1m8_blind_spawn"
    assert handler.pick_round_scenario_id(3, {}) == "duel_e1m8"  # wraps


def test_pick_round_scenario_id_randomizes_choice_when_flagged():
    import random

    random.seed(0)
    handler = make_handler_with_state(
        randomize_spawns=True,
        scenario_pool=["duel_e1m8", "duel_e1m8_blind_spawn"],
    )
    seen = {handler.pick_round_scenario_id(i, {}) for i in range(1, 20)}
    # With 19 rolls over 2 choices, we should see both at least once.
    assert seen == {"duel_e1m8", "duel_e1m8_blind_spawn"}


def test_pick_round_scenario_id_with_empty_pool_falls_back_to_payload():
    handler = make_handler_with_state(scenario_pool=[])
    chosen = handler.pick_round_scenario_id(1, {"scenario_id": "duel_e1m8_blind_spawn"})
    assert chosen == "duel_e1m8_blind_spawn"


# ---------- Multi-map scenario constants ----------


def test_duel_scenarios_contains_minimum_set():
    scenario_ids = {entry["scenario_id"] for entry in server.DUEL_SCENARIOS}
    # Two buildable scenarios shipped today
    assert "duel_e1m8" in scenario_ids
    assert "duel_e1m8_blind_spawn" in scenario_ids
    # Two future scenarios reserved for WASM rebuild
    assert "duel_e1m8_corner_spawn" in scenario_ids
    assert "duel_e1m8_center_spawn" in scenario_ids


def test_duel_active_scenario_ids_includes_all_built_scenarios():
    active = server.DUEL_ACTIVE_SCENARIO_IDS
    assert active == {
        "duel_e1m8",
        "duel_e1m8_blind_spawn",
        "duel_e1m8_corner_spawn",
        "duel_e1m8_center_spawn",
    }


# ---------- Hierarchical strategy expansion ----------


def test_strategy_expansion_valid_for_all_category_actions():
    from doom_arena_strategy import STRATEGY_ACTIONS, expand_strategy

    handler = make_handler_with_state()
    issued = (__import__("time").time_ns() // 1_000_000) + 10000
    for category, actions in STRATEGY_ACTIONS.items():
        for action in actions:
            payload = expand_strategy(
                participant_id="player_1",
                category=category,
                action=action,
                intensity="medium",
                commit_ms=3000,
                sequence_number=1,
            )
            payload.update({"issued_at_ms": issued, "expires_at_ms": issued + int(payload["duration_ms"])})
            row = handler.normalize_participant_intent(payload)
            assert row["intent"] in {"engage_opponent", "strafe_attack", "hold", "search"}
            assert row["strategy_source"] == "hierarchical"
            assert row["strategy_category"] == category
            assert row["strategy_action"] == action


def test_strategy_expansion_rejects_invalid_category_action_combo():
    import pytest
    from doom_arena_strategy import expand_strategy

    with pytest.raises(ValueError, match="action must be one of"):
        expand_strategy(
            participant_id="player_1",
            category="engage",
            action="patrol_left",
            intensity="medium",
            commit_ms=3000,
        )


def test_strategy_expansion_clamps_commit_ms_and_preserves_metadata():
    from doom_arena_strategy import expand_strategy

    payload = expand_strategy(
        participant_id="player_1",
        category="engage",
        action="strafe_fight",
        intensity="high",
        commit_ms=99999,
        sequence_number=7,
    )
    assert payload["duration_ms"] == 8000
    assert payload["strategy_commit_ms"] == 8000
    assert payload["strategy_intensity"] == "high"
    assert payload["sequence_number"] == 7
    assert payload["intent"] == "strafe_attack"

    payload = expand_strategy(
        participant_id="player_1",
        category="engage",
        action="strafe_fight",
        intensity="low",
        commit_ms=1,
        sequence_number=8,
    )
    assert payload["duration_ms"] == 3000
    assert payload["strategy_commit_ms"] == 3000

# ---------- Phase 1: previous-round recap ----------


def test_build_previous_rounds_recap_empty_on_round_1(tmp_path, monkeypatch):
    import doom_arena_server as srv
    monkeypatch.setattr(srv, "RESULTS_ROOT", tmp_path)
    handler = make_handler_with_state()
    result = handler.build_previous_rounds_recap("player_1", 1, "session_abc", window=2)
    assert result == []


def test_build_previous_rounds_recap_reads_summary(tmp_path, monkeypatch):
    import doom_arena_server as srv
    monkeypatch.setattr(srv, "RESULTS_ROOT", tmp_path)
    session_dir = tmp_path / "session_abc"
    round_dir = session_dir / "round_01_run_xyz"
    round_dir.mkdir(parents=True)
    summary = {
        "round": 1, "winner": "player_1", "terminal_reason": "player_2_dead",
        "elapsed_time_seconds": 15.0, "scenario_id": "duel_e1m8",
        "player_1_health_end": 100, "player_2_health_end": 0,
        "player_1_damage_dealt": 150, "player_2_damage_dealt": 20,
        "player_1_shots_fired": 10, "player_1_shots_hit": 5,
        "player_2_shots_fired": 8, "player_2_shots_hit": 1,
    }
    (round_dir / "summary.json").write_text(
        __import__("json").dumps(summary), encoding="utf-8"
    )
    handler = make_handler_with_state()
    result = handler.build_previous_rounds_recap("player_1", 2, "session_abc", window=2)
    assert len(result) == 1
    assert result[0]["winner"] == "player_1"
    assert result[0]["your_final_health"] == 100
    assert result[0]["opponent_final_health"] == 0
    assert result[0]["your_hit_rate"] == 0.5


def test_build_previous_rounds_recap_respects_window(tmp_path, monkeypatch):
    import doom_arena_server as srv
    monkeypatch.setattr(srv, "RESULTS_ROOT", tmp_path)
    session_dir = tmp_path / "session_abc"
    for i in range(1, 5):
        rd = session_dir / f"round_0{i}_run_x{i}"
        rd.mkdir(parents=True)
        (rd / "summary.json").write_text(
            __import__("json").dumps({"round": i, "winner": "player_1"}), encoding="utf-8"
        )
    handler = make_handler_with_state()
    result = handler.build_previous_rounds_recap("player_1", 5, "session_abc", window=2)
    assert len(result) == 2
    assert result[0]["round"] == 3
    assert result[1]["round"] == 4


# ---------- Phase 3b: blueprint loader ----------


def test_load_map_blueprint_returns_content_for_known_scenario():
    from doom_arena_duel_prompts import load_map_blueprint
    blueprint = load_map_blueprint("duel_e1m8")
    assert len(blueprint) > 0
    assert "duel_e1m8" in blueprint.lower() or "e1m8" in blueprint.lower()


def test_load_map_blueprint_returns_empty_for_unknown_scenario():
    from doom_arena_duel_prompts import load_map_blueprint
    blueprint = load_map_blueprint("nonexistent_scenario_xyz")
    assert blueprint == ""


def test_map_blueprint_section_injected_in_prompt():
    from doom_arena_duel_prompts import instructions
    prompt = instructions(
        participant_id="player_1",
        model="test",
        opponent_id="player_2",
        controller_token="tok",
        enforce_tokens=False,
        enable_map_blueprint=True,
        scenario_id="duel_e1m8",
    )
    assert "Map blueprint" in prompt
    assert "bounds" in prompt.lower() or "grid" in prompt.lower()


def test_map_blueprint_absent_when_flag_off():
    from doom_arena_duel_prompts import instructions
    prompt = instructions(
        participant_id="player_1",
        model="test",
        opponent_id="player_2",
        controller_token="tok",
        enforce_tokens=False,
        enable_map_blueprint=False,
        scenario_id="duel_e1m8",
    )
    assert "Map blueprint" not in prompt


# ---------- Phase 1: prompt sections ----------


def test_cross_round_section_present_when_flag_on():
    from doom_arena_duel_prompts import instructions
    prompt = instructions(
        participant_id="player_1",
        model="test",
        opponent_id="player_2",
        controller_token="tok",
        enforce_tokens=False,
        total_rounds=3,
        enable_cross_round_recap=True,
    )
    assert "previous_rounds" in prompt
    assert "Cross-round learning" in prompt


def test_cross_round_section_absent_when_single_round():
    from doom_arena_duel_prompts import instructions
    prompt = instructions(
        participant_id="player_1",
        model="test",
        opponent_id="player_2",
        controller_token="tok",
        enforce_tokens=False,
        total_rounds=1,
        enable_cross_round_recap=True,
    )
    assert "previous_rounds" not in prompt


def test_post_finish_stop_rule_always_present():
    from doom_arena_duel_prompts import instructions
    prompt = instructions(
        participant_id="player_1",
        model="test",
        opponent_id="player_2",
        controller_token="tok",
        enforce_tokens=False,
    )
    assert "stop all tool calls immediately" in prompt



