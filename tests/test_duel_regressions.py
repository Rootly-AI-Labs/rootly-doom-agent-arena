import subprocess
import sys
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import doom_arena_server as server


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_script(script_name: str) -> None:
    script_path = REPO_ROOT / "scripts" / script_name
    subprocess.run(
        [sys.executable, str(script_path)],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def make_handler(run_id: str = "run_test", scenario_id: str = "duel_e1m8"):
    handler = server.DoomArenaHandler.__new__(server.DoomArenaHandler)
    handler.server = SimpleNamespace(
        run_id=run_id,
        scenario_id=scenario_id,
        stats_lock=threading.Lock(),
        latest_intent_by_participant={},
    )
    return handler


def test_participant_intent_parser_smoke_regressions() -> None:
    run_script("smoke_participant_intents_parser.py")


def test_participant_autopilot_smoke_regressions() -> None:
    run_script("smoke_participant_autopilot.py")


def test_update_participant_intent_row_preserves_other_participant(tmp_path, monkeypatch) -> None:
    intent_path = tmp_path / "arena_participant_intents.local.tsv"
    monkeypatch.setattr(server, "ARENA_PARTICIPANT_INTENT_TSV", intent_path)
    handler = make_handler()

    p1 = handler.normalize_participant_intent(
        {
            "participant_id": "player_1",
            "intent": "engage_opponent",
            "style": "balanced",
            "target_id": "player_2",
            "preferred_distance": 600,
            "aggression": 0.5,
            "duration_ms": 25000,
            "sequence_number": 1,
        }
    )
    p2 = handler.normalize_participant_intent(
        {
            "participant_id": "player_2",
            "intent": "strafe_attack",
            "style": "aggressive",
            "target_id": "player_1",
            "preferred_distance": 500,
            "aggression": 0.7,
            "duration_ms": 25000,
            "sequence_number": 3,
        }
    )

    intent_path.write_text(handler.participant_intent_rows_to_tsv([p1, p2]), encoding="utf-8")

    updated_p1 = handler.normalize_participant_intent(
        {
            "participant_id": "player_1",
            "intent": "search",
            "style": "balanced",
            "target_id": "player_2",
            "preferred_distance": 600,
            "aggression": 0.5,
            "duration_ms": 25000,
            "sequence_number": 4,
        }
    )

    text = handler.update_participant_intent_row(updated_p1)
    rows = handler.parse_participant_intent_rows(text, reject_expired=False)

    assert {row["participant_id"] for row in rows} == {"player_1", "player_2"}
    assert next(row for row in rows if row["participant_id"] == "player_1")["intent"] == "search"
    assert next(row for row in rows if row["participant_id"] == "player_2")["intent"] == "strafe_attack"


def test_update_participant_intent_row_drops_only_expired_other_rows(tmp_path, monkeypatch) -> None:
    intent_path = tmp_path / "arena_participant_intents.local.tsv"
    monkeypatch.setattr(server, "ARENA_PARTICIPANT_INTENT_TSV", intent_path)
    handler = make_handler()

    monkeypatch.setattr(server, "now_ms", lambda: 10_000)
    intent_path.write_text(
        server.PARTICIPANT_INTENT_HEADER
        + "run_test\tduel_e1m8\texpired_p2\t1000\t2000\tplayer_2\thold\tcautious\tplayer_1\t600\t0.5\t1000\tauto\tdirect\tonly_when_aligned\tmaintain\t\t1\t\t\t\t\t\t\t\t\tsweep\tdefault\t\tauto\topponent\tauto\n",
        encoding="utf-8",
    )

    new_p1 = handler.normalize_participant_intent(
        {
            "participant_id": "player_1",
            "intent": "engage_opponent",
            "style": "balanced",
            "target_id": "player_2",
            "preferred_distance": 600,
            "aggression": 0.5,
            "duration_ms": 25000,
            "sequence_number": 2,
        }
    )

    text = handler.update_participant_intent_row(new_p1)
    rows = handler.parse_participant_intent_rows(text, reject_expired=False)

    assert [row["participant_id"] for row in rows] == ["player_1"]


def test_current_run_participant_intents_merge_file_and_memory(tmp_path, monkeypatch) -> None:
    intent_path = tmp_path / "arena_participant_intents.local.tsv"
    monkeypatch.setattr(server, "ARENA_PARTICIPANT_INTENT_TSV", intent_path)
    monkeypatch.setattr(server, "now_ms", lambda: 10_000)
    handler = make_handler()

    p1 = handler.normalize_participant_intent(
        {
            "participant_id": "player_1",
            "intent": "engage_opponent",
            "style": "balanced",
            "target_id": "player_2",
            "preferred_distance": 600,
            "aggression": 0.5,
            "duration_ms": 25000,
            "issued_at_ms": 9_000,
            "sequence_number": 1,
        }
    )
    p2 = handler.normalize_participant_intent(
        {
            "participant_id": "player_2",
            "intent": "strafe_attack",
            "style": "aggressive",
            "target_id": "player_1",
            "preferred_distance": 500,
            "aggression": 0.7,
            "duration_ms": 25000,
            "issued_at_ms": 9_500,
            "sequence_number": 2,
        }
    )

    intent_path.write_text(handler.participant_intent_rows_to_tsv([p1]), encoding="utf-8")
    handler.server.latest_intent_by_participant = {
        "player_2": {
            "run_id": "run_test",
            "scenario_id": "duel_e1m8",
            **p2,
        }
    }

    rows = handler.current_run_participant_intent_rows()

    assert {row["participant_id"] for row in rows} == {"player_1", "player_2"}
    assert next(row for row in rows if row["participant_id"] == "player_2")["intent"] == "strafe_attack"


def test_get_participant_intents_endpoint_returns_tsv(tmp_path, monkeypatch) -> None:
    intent_path = tmp_path / "arena_participant_intents.local.tsv"
    monkeypatch.setattr(server, "ARENA_PARTICIPANT_INTENT_TSV", intent_path)
    monkeypatch.setattr(server, "now_ms", lambda: 10_000)
    handler = make_handler()
    handler.path = "/api/arena/participant-intents"
    handler.wfile = BytesIO()

    response_meta: dict[str, object] = {}
    headers: list[tuple[str, str]] = []
    handler.send_response = lambda status: response_meta.__setitem__("status", status)
    handler.send_header = lambda name, value: headers.append((name, value))
    handler.end_headers = lambda: None

    p1 = handler.normalize_participant_intent(
        {
            "participant_id": "player_1",
            "intent": "engage_opponent",
            "style": "balanced",
            "target_id": "player_2",
            "preferred_distance": 600,
            "aggression": 0.5,
            "duration_ms": 25000,
            "issued_at_ms": 9_000,
            "sequence_number": 1,
        }
    )
    intent_path.write_text(handler.participant_intent_rows_to_tsv([p1]), encoding="utf-8")

    handler.do_GET()

    body = handler.wfile.getvalue().decode("utf-8")
    assert response_meta["status"] == server.HTTPStatus.OK
    assert ("Content-Type", "text/tab-separated-values; charset=utf-8") in headers
    assert "participant_id\tintent" in body
    assert "player_1\tengage_opponent" in body


def test_duel_player_1_remains_in_real_player_tick_path() -> None:
    arena_duel = (REPO_ROOT / "src" / "doom" / "arena_duel.c").read_text(encoding="utf-8")
    g_game = (REPO_ROOT / "src" / "doom" / "g_game.c").read_text(encoding="utf-8")
    player_control = (REPO_ROOT / "src" / "doom" / "arena_player_control.c").read_text(encoding="utf-8")

    assert "Arena_DuelModeEnabled() && gamemap == 8" in g_game
    assert "playeringame[consoleplayer] = true;" in g_game
    assert "ArenaDuel_RestorePlayer1Mobj();" in player_control
    assert "Arena_LoadRunMetadata();" in player_control
    assert "Arena_LoadRunMetadata();" in arena_duel


def test_duel_player_1_retains_last_autopilot_command_briefly() -> None:
    player_control = (REPO_ROOT / "src" / "doom" / "arena_player_control.c").read_text(encoding="utf-8")

    assert "arena_player_last_autopilot_command_ms" in player_control
    assert "retaining_last_autopilot_command" in player_control
