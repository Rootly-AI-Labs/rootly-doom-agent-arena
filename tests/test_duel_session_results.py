import json
from io import BytesIO
from pathlib import Path
import pytest

import doom_arena_server as server
from tests.test_duel_regressions import make_handler

def test_read_duel_session_results(tmp_path, monkeypatch):
    # Mock RESULTS_ROOT to point to tmp_path
    monkeypatch.setattr(server, "RESULTS_ROOT", tmp_path)
    
    # Create mock duel session results structure
    session_id = "session_123"
    session_dir = tmp_path / session_id
    session_dir.mkdir()
    
    # Create round_01 and round_02 directories
    r1_dir = session_dir / "round_01_runA"
    r1_dir.mkdir()
    (r1_dir / "summary.json").write_text(json.dumps({
        "round": 1,
        "winner": "player_1",
        "terminal_reason": "frag",
        "elapsed_time_seconds": 15,
        "player_1_health_end": 100,
        "player_2_health_end": 0,
        "player_1_damage_dealt": 150,
        "player_2_damage_dealt": 20,
        "player_1_shots_fired": 10,
        "player_1_shots_hit": 5,
        "player_2_shots_fired": 8,
        "player_2_shots_hit": 1,
    }), encoding="utf-8")
    
    r2_dir = session_dir / "round_02_runB"
    r2_dir.mkdir()
    (r2_dir / "summary.json").write_text(json.dumps({
        "round": 2,
        "winner": "player_2",
        "terminal_reason": "time_limit",
        "elapsed_time_seconds": 60,
        "player_1_health_end": 50,
        "player_2_health_end": 80,
        "player_1_damage_dealt": 40,
        "player_2_damage_dealt": 70,
        "player_1_shots_fired": 20,
        "player_1_shots_hit": 4,
        "player_2_shots_fired": 25,
        "player_2_shots_hit": 8,
    }), encoding="utf-8")
    
    # Setup handler
    handler = make_handler()
    handler.path = f"/api/arena/duel-session-results?duel_session_id={session_id}"
    handler.wfile = BytesIO()
    
    # Setup server values
    handler.server.duel_session_id = session_id
    handler.server.duel_total_rounds = 2
    handler.server.player_1_model = "test_p1_model"
    handler.server.player_2_model = "test_p2_model"
    
    response_meta = {}
    headers = []
    handler.send_response = lambda status: response_meta.__setitem__("status", status)
    handler.send_header = lambda name, value: headers.append((name, value))
    handler.end_headers = lambda: None
    
    # Run do_GET which calls read_duel_session_results
    handler.do_GET()
    
    assert response_meta["status"] == server.HTTPStatus.OK
    body = json.loads(handler.wfile.getvalue().decode("utf-8"))
    
    assert body["ok"] is True
    assert body["duel_session_id"] == session_id
    assert body["total_rounds"] == 2
    assert body["player_1_model"] == "test_p1_model"
    assert body["player_2_model"] == "test_p2_model"
    
    rounds = body["rounds"]
    assert len(rounds) == 2
    assert rounds[0]["round"] == 1
    assert rounds[0]["winner"] == "player_1"
    assert rounds[1]["round"] == 2
    assert rounds[1]["winner"] == "player_2"
