import json
import subprocess
import sys
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import doom_arena_server as server
import pytest


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
        participant_ready_agents={},
        participant_agent_names={},
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
        + "run_test\tduel_e1m8\texpired_p2\t1000\t2000\tplayer_2\thold\tcautious\tplayer_1\t600\t0.5\t1000\tauto\tdirect\tonly_when_aligned\tmaintain\t\t1\t\t\t\t\t\t\t\t\tsweep\tdefault\t\tauto\topponent\tauto\thold\t\t\t\t\t\n",
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


def test_duel_dashboard_tracks_equipment_and_guards_completed_reload() -> None:
    index = (REPO_ROOT / "src" / "index.html").read_text(encoding="utf-8-sig")
    browser_runtime = (REPO_ROOT / "src" / "websockets-doom.js").read_text(encoding="utf-8")
    logo = REPO_ROOT / "src" / "assets" / "rootly-ai-logo-white.png"
    favicon = REPO_ROOT / "src" / "assets" / "rootly-favicon.svg"
    player_1_card = index.split('id="player-1-pov-card"', 1)[1].split('id="player-2-pov-card"', 1)[0]
    player_2_card = index.split('id="player-2-pov-card"', 1)[1].split('id="duel-play-footer"', 1)[0]

    assert 'id="arena-launcher-title">Rootly Doom Agent Arena</h1>' in index
    assert "Set up both MCP agents, then start the benchmark." not in index
    assert "Prompt synced" not in index
    assert 'id="duel-prompt-change-indicator" hidden' in index
    assert "<title>Rootly Doom Agent Arena</title>" in index
    assert "document.title = 'Rootly Doom Agent Arena'" in browser_runtime
    assert "document.title = title" not in browser_runtime
    assert 'script.src = "websockets-doom.js?v=" + doomAssetCacheBust' in index
    assert 'href="assets/rootly-favicon.svg"' in index
    assert 'setLauncherCopy("Doom Arena Duel"' not in index
    assert 'id="duel-p1-equipment-icons"' in index
    assert 'id="duel-p2-equipment-icons"' in index
    assert 'id="duel-p1-health"' not in index
    assert 'id="duel-p2-health"' not in index
    assert 'id="duel-p1-health-label">❤️ 150 / 150</div>' in index
    assert 'id="duel-p2-health-label">❤️ 150 / 150</div>' in index
    assert 'label.textContent = "❤️ " + health + " / " + DUEL_MAX_HEALTH' in index
    assert 'label.textContent = "HP "' not in index
    assert 'id="duel-p1-damage"' not in index
    assert 'id="duel-p2-damage"' not in index
    assert "duel-stat-grid" not in index
    assert "duel-stat-card" not in index
    assert "function renderDuelEquipmentIcons" in index
    assert 'className = "duel-equipment-icon shotgun"' in index
    assert 'className = "duel-equipment-icon health-pack"' in index
    assert "var DUEL_PICKUP_GLOW_MS = 5000;" in index
    assert "function updateDuelEquipmentPickupGlow" in index
    assert 'icon.classList.add("is-recent-pickup")' in index
    assert "animation: duelEquipmentPickupGlow 5s ease-out both;" in index
    assert "@keyframes duelEquipmentPickupGlow" in index
    assert 'class="duel-stat-label">Shotgun</span>' not in index
    assert 'class="duel-stat-label">Health packs</span>' not in index
    assert 'id="duel-tactical-match-progress">1/1</div>' in index
    assert '<h1 id="duel-stream-title">AI Fighting</h1>' in index
    stream_title_css = index.split("#container.duel-layout-active #duel-stream-title {", 1)[1].split("}", 1)[0]
    assert "grid-column: 1 / -1;" in stream_title_css
    assert "grid-row: 1;" in stream_title_css
    assert "font-size: 42px;" in stream_title_css
    assert "font-weight: 800;" in stream_title_css
    assert "min-height: 94px;" in stream_title_css
    assert "border-bottom: 1px solid var(--arena-panel-border-strong);" in stream_title_css
    assert "font-family: var(--arena-title-font) !important;" in stream_title_css
    assert 'font-family: "Tourney";' in index
    assert '--arena-title-font: "Tourney", "Arial Black", sans-serif;' in index
    duel_layout_css = index.split("#container.duel-layout-active {", 1)[1].split("}", 1)[0]
    assert "grid-template-rows: 94px auto;" in duel_layout_css
    assert "align-content: start;" in duel_layout_css
    tactical_panel_markup = index.split('id="duel-tactical-panel"', 1)[1].split(
        'id="duel-pov-grid"', 1
    )[0]
    assert tactical_panel_markup.index('id="duel-tactical-match-score"') < tactical_panel_markup.index(
        'class="duel-tactical-shell"'
    )
    assert tactical_panel_markup.index('id="duel-tactical-match-score"') < tactical_panel_markup.index(
        'class="duel-tactical-credit duel-tactical-score-credit"'
    )
    assert tactical_panel_markup.index('class="duel-tactical-credit duel-tactical-score-credit"') < tactical_panel_markup.index(
        'class="duel-tactical-shell"'
    )
    assert tactical_panel_markup.index('id="duel-tactical-match-score"') < tactical_panel_markup.index(
        'id="duel-tactical-match-progress"'
    )
    score_card_css = index.split(".duel-tactical-score-card {", 1)[1].split("}", 1)[0]
    assert "width: 52%;" in score_card_css
    assert "margin: 0 auto 12px;" in score_card_css
    assert "border-radius: 10px;" in score_card_css
    tactical_meta_card_css = index.split(".duel-tactical-meta-card {", 1)[1].split("}", 1)[0]
    assert "text-align: center;" in tactical_meta_card_css
    assert 'id="duel-tactical-elapsed">0s</div>' in index
    assert 'Math.floor(Math.max(0, benchmarkNumber(elapsed, 0))) + "s"' in index
    assert '"Elapsed " + Math.floor' not in index
    assert 'id="duel-tactical-coordinate-tooltip"' not in index
    assert "installTacticalOverlayCoordinateTooltip" not in index
    assert 'ctx.fillText(String(col + 1).padStart(2, "0")' not in index
    assert 'ctx.fillText(String.fromCharCode("A".charCodeAt(0) + row)' not in index
    assert 'id="duel-tactical-match-streak"' not in index
    assert 'id="duel-tactical-latest-match"' not in index
    assert ">Tactical overlay</div>" not in index
    assert "function funAgentName(identityLabel, fallback)" in index
    assert "function renderColoredAgentIdentity(elementId, identityLabel, fallback, participantId)" in index
    assert 'renderPovAgentIdentity("player-1", assistant1, "Player 1", currentPlayer1Model, "player_1")' in index
    assert 'renderPovAgentIdentity("player-2", assistant2, "Player 2", currentPlayer2Model, "player_2")' in index
    assert "function parseAgentIdentity(identityLabel, fallbackName, fallbackModel)" in index
    assert 'id="player-1-model-name"' in index
    assert 'id="player-1-harness-name"' in index
    assert 'id="player-2-model-name"' in index
    assert 'id="player-1-model-provider" hidden' in index
    assert 'id="player-2-model-provider" hidden' in index
    assert "function modelProviderFor(modelName)" in index
    assert "function renderModelProvider(prefix, modelName)" in index
    assert 'renderModelProvider(prefix, identity.model);' in index
    assert 'label: "Anthropic"' in index
    assert 'logo: "assets/anthropic-mark.svg"' in index
    assert 'label: "OpenAI"' in index
    assert 'logo: "assets/openai-mark.svg"' in index
    assert (REPO_ROOT / "src" / "assets" / "anthropic-mark.svg").is_file()
    assert (REPO_ROOT / "src" / "assets" / "openai-mark.svg").is_file()
    assert 'id="player-2-harness-name"' in index
    assert index.count('class="duel-agent-identity-meta-label">model</span>') == 2
    assert index.count('class="duel-agent-identity-meta-label">harness</span>') == 2
    identity_meta_css = index.split(".duel-agent-identity-meta {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: repeat(2, max-content);" in identity_meta_css
    assert "gap: 38px;" in identity_meta_css
    assert player_1_card.index('id="player-1-model-name"') < player_1_card.index(">model</span>")
    assert player_1_card.index('id="player-1-harness-name"') < player_1_card.index(">harness</span>")
    assert player_2_card.index('id="player-2-model-name"') < player_2_card.index(">model</span>")
    assert player_2_card.index('id="player-2-harness-name"') < player_2_card.index(">harness</span>")
    assert index.count('class="duel-agent-chosen-label">model chosen name</span>') == 2
    assert "font: 700 clamp(18px, 1.45vw, 22px)" in index
    assert "#player-1-pov-card .duel-agent-name-line {" in index
    assert "align-items: flex-end;" in index
    assert "#player-2-pov-card .duel-agent-name-line {" in index
    assert "align-items: flex-start;" in index
    chosen_label_css = index.split(".duel-agent-chosen-label {", 1)[1].split("}", 1)[0]
    assert "border" not in chosen_label_css
    assert "background" not in chosen_label_css
    assert "flex-direction: column;" in index
    assert player_1_card.index('class="duel-agent-chosen-label"') < player_1_card.index('id="player-1-pov-title"')
    assert player_2_card.index('class="duel-agent-chosen-label"') < player_2_card.index('id="player-2-pov-title"')
    assert player_1_card.index('id="player-1-model-provider"') < player_1_card.index('id="player-1-pov-title"')
    assert player_2_card.index('id="player-2-pov-title"') < player_2_card.index('id="player-2-model-provider"')
    provider_badge_css = index.split(".duel-model-provider {", 1)[1].split("}", 1)[0]
    provider_logo_css = index.split(".duel-model-provider-logo {", 1)[1].split("}", 1)[0]
    assert "min-height: 42px;" in provider_badge_css
    assert "font-size: 14px;" in provider_badge_css
    assert "width: 28px;" in provider_logo_css
    assert "height: 28px;" in provider_logo_css
    assert player_1_card.index('class="duel-pov-frame"') < player_1_card.index('id="duel-p1-log-total"') < player_1_card.index('id="duel-p1-log"')
    assert player_2_card.index('class="duel-pov-frame"') < player_2_card.index('id="duel-p2-log-total"') < player_2_card.index('id="duel-p2-log"')
    assert 'class="duel-agent-decision-metrics"' in player_1_card
    assert 'class="duel-agent-decision-metrics"' in player_2_card
    assert player_1_card.count('class="duel-pov-metrics-row"') == 1
    assert player_2_card.count('class="duel-pov-metrics-row"') == 1
    assert player_1_card.count('class="duel-agent-opposite"') == 1
    assert player_2_card.count('class="duel-agent-opposite"') == 1
    assert "#player-1-pov-card .duel-agent-opposite {" in index
    assert "#player-2-pov-card .duel-agent-opposite {" in index
    assert 'Player 1 battle thoughts <span' not in index
    assert 'Player 2 battle thoughts <span' not in index
    assert "#player-1-pov-card .duel-agent-identity-meta {" in index
    assert "#player-2-pov-card .duel-agent-identity-meta {" in index
    identity_header_css = index.split(".duel-agent-identity-header {", 1)[1].split("}", 1)[0]
    assert "border" not in identity_header_css
    round_progress_names = index.split('setText("round-progress-round-label"', 1)[1].split(
        'setText("round-progress-score"', 1
    )[0]
    round_progress_renderer = index.split(
        "function renderRoundProgressPopup", 1
    )[1].split("function loadRoundProgressPopup", 1)[0]
    assert "var name1 = funAgentName(" in round_progress_renderer
    assert "var name2 = funAgentName(" in round_progress_renderer
    assert '"round-progress-name-1",\n                    name1,' in round_progress_names
    assert '"round-progress-name-2",\n                    name2,' in round_progress_names
    assert ".duel-agent-name.player-1 {" in index
    assert "color: #7ddcff;" in index
    assert ".duel-agent-name.player-2 {" in index
    assert "color: #ff7a7a;" in index
    assert ".duel-agent-status[hidden]" in index
    assert 'status.textContent = connected ? "" : "Waiting for agent"' in index
    assert "status.hidden = !!connected" in index
    assert 'status.textContent = connected ? "Agent ready"' not in index
    waiting_overlay_css = index.split(".duel-command-waiting-overlay {", 1)[1].split("}", 1)[0]
    assert "color: #ffce6b;" in waiting_overlay_css
    assert "color: #7ddcff;" not in waiting_overlay_css
    assert "duel-tactical-map-header" not in index
    assert "duel-tactical-legend" not in index
    assert "duel-tactical-swatch" not in index
    assert 'class="duel-tactical-vs" aria-label="Versus"' in index
    assert 'id="player-1-versus-provider" hidden' in index
    assert 'id="player-2-versus-provider" hidden' in index
    assert '<span class="duel-tactical-vs-label">VS</span>' in index
    assert ".duel-versus-provider.player-1 {" in index
    assert ".duel-versus-provider.player-2 {" in index
    assert "renderProviderBadge(document.getElementById(prefix + \"-versus-provider\"), provider);" in index
    assert '<span class="player-1">V</span><span class="player-2">S</span>' not in index
    assert "benchmark-score-crown" in index
    assert 'winnerNode.textContent = winningSide ? winningName + " wins" : "Match drawn"' in index
    assert 'id="benchmark-results-competitors"' not in index
    assert ".benchmark-competitor" not in index
    assert ".benchmark-player-1 {" in index
    assert ".benchmark-player-2 {" in index
    assert 'scoreText = p2Wins + "–" + p1Wins' not in index
    assert '"<span>A · " + h1' not in index
    assert 'id="player-1-battle-quip"' in index
    assert 'id="player-2-battle-quip"' in index
    assert "duel-pov-model-overlay" not in index
    assert "setPovModelOverlay" not in index
    assert player_1_card.index('id="player-1-pov-title"') < player_1_card.index('id="duel-p1-equipment-icons"') < player_1_card.index('id="duel-p1-health-bar"') < player_1_card.index('class="duel-pov-frame"')
    assert player_2_card.index('id="player-2-pov-title"') < player_2_card.index('id="duel-p2-equipment-icons"') < player_2_card.index('id="duel-p2-health-bar"') < player_2_card.index('class="duel-pov-frame"')
    pov_frame_css = index.split(".duel-pov-frame {", 1)[1].split("}", 1)[0]
    assert "outline: 1px solid var(--duel-pov-border-color);" in pov_frame_css
    assert "outline: 4px" not in pov_frame_css
    assert "#player-1-pov-card .duel-pov-frame" in index
    assert "--duel-pov-border-color: #7ddcff;" in index
    assert "#player-2-pov-card .duel-pov-frame" in index
    assert "--duel-pov-border-color: #ff7a7a;" in index
    assert ".duel-pov-card.llm-connected .duel-pov-frame" not in index
    assert ".duel-pov-card.llm-disconnected .duel-pov-frame" not in index
    assert 'duelBattleQuipForParticipant("player_1", player1)' in index
    assert 'duelBattleQuipForParticipant("player_2", player2)' in index
    assert "row.participant_id === participantId && row.plan_summary" in index
    assert "matchingIntent.intent_id || matchingIntent.sequence_number" in index
    assert "function repairLegacyBattleQuipEncoding" in index
    assert '.replace(/\\uFFFD{3}/g, "—")' in index
    assert "DUEL_BATTLE_QUIP_DISPLAY_MS" not in index
    assert "duelBattleQuipTimerByParticipant" not in index
    assert ".duel-battle-quip-overlay {" in index
    quip_css = index.split(".duel-battle-quip-overlay {", 1)[1].split("}", 1)[0]
    assert "top: 18px;" in quip_css
    assert "bottom:" not in quip_css
    assert "animation: duelBattleQuipIn 180ms ease-out both;" in index
    assert "translate(-50%, -10px) scale(0.96)" in index
    assert "DUEL_ROUND_SUMMARY_HOLD_MS = 5000" in index
    assert "roundProgressShownAtByRun[runId] = Date.now()" in index
    assert "summaryHoldRemainingMs" in index
    assert "Next match starts automatically in 5 seconds" in index
    assert '"Match " + currentRound + " of " + totalRounds' not in index
    assert 'currentRound + "/" + totalRounds' in index
    assert "function updateDuelPickupCountsFromEvents" in index
    assert "function drawTacticalShotgunIcon" in index
    assert "function traceTacticalShotgunSilhouette" in index
    assert "drawTacticalShotgunIcon(ctx, screen.x, screen.y)" in index
    assert "ctx.fillText(marker.label" not in index
    assert 'pickup.type === "weapon" ? "S"' not in index
    assert 'rejected: "MCP command rejected"' in index
    assert '"Why it was rejected: " + entry.error' in index
    assert "Couldn't execute" not in index
    assert "Raw error:" not in index
    assert "function duelRunAlreadyRecordedAsComplete" in index
    assert 'id="duel-header"' not in index
    assert 'id="duel-title"' not in index
    assert "renderDuelTitle" not in index
    assert 'id="duel-menu"' in index
    assert 'href="https://github.com/Rootly-AI-Labs/doom-benchmark"' in index
    assert 'class="duel-play-footer-brand"' in index
    assert 'class="duel-play-footer-logo"' in index
    assert 'src="assets/rootly-ai-logo-white.png"' in index
    assert 'class="duel-play-footer-actions"' in index
    tactical_credit = index.split('class="duel-tactical-credit duel-tactical-score-credit"', 1)[1].split('id="duel-pov-grid"', 1)[0]
    play_footer = index.split('id="duel-play-footer"', 1)[1].split('id="arena-duel-dashboard"', 1)[0]
    assert "Brought to you by" in tactical_credit
    assert ">Rootly Ai Labs<" not in tactical_credit
    assert 'aria-label="Rootly AI Labs"' in tactical_credit
    assert "Built with <strong>Codex</strong>" not in tactical_credit
    assert 'class="duel-play-footer-logo"' in tactical_credit
    assert "Built with <strong>Codex</strong>" not in play_footer
    assert 'class="duel-play-footer-logo"' not in play_footer
    assert ">Built by Rootly AI Labs</a>" not in index
    tactical_layout = index.split("#container.duel-layout-active #duel-tactical-panel {", 1)[1].split("}", 1)[0]
    assert "grid-column: 2;" in tactical_layout
    assert "grid-row: 2;" in tactical_layout
    assert logo.is_file()
    assert logo.stat().st_size > 0
    assert favicon.is_file()
    assert favicon.stat().st_size > 0
    assert "#duel-p1-prompt-card .duel-prompt-title" in index
    assert "#duel-p2-prompt-card .duel-prompt-title" in index
    assert 'playerClass: "player-1"' in index
    assert 'playerClass: "player-2"' in index


def test_duel_pov_refresh_loop_recovers_from_individual_render_errors() -> None:
    index = (REPO_ROOT / "src" / "index.html").read_text(encoding="utf-8-sig")

    assert "duelPovAnimationFrame = 0;" in index
    assert "Player 1 POV refresh failed" in index
    assert "tactical automap refresh failed" in index
    assert "Player 2 POV refresh failed" in index
    assert "requestAnimationFrame(refreshDuelPovsOnAnimationFrame)" in index


def test_duel_preview_mode_uses_fixture_state_without_starting_doom() -> None:
    index = (REPO_ROOT / "src" / "index.html").read_text(encoding="utf-8-sig")
    layout_svg = (REPO_ROOT / "src" / "assets" / "duel_room_layout.svg").read_text(
        encoding="utf-8"
    )
    initializer = index.split("function initializeArenaLauncher()", 1)[1].split(
        "var Module =", 1
    )[0]

    assert 'get("duelPreview")' in index
    assert 'document.documentElement.classList.add("duel-autostart", "duel-preview")' in index
    assert "function initializeDuelPreview" in index
    assert "function duelPreviewFixtures" in index
    assert "function syncDuelPreviewStreamFrame" in index
    assert "function moveDuelPreviewControlsOutsideFrame" in index
    assert "window.innerWidth / streamWidth" in index
    assert "window.innerHeight / streamHeight" in index
    assert 'width: 1920px;' in index
    assert 'height: 1080px;' in index
    assert 'border: 1px solid #ff0000;' in index
    preview_frame_css = index.split("html.duel-preview #container.duel-layout-active {", 1)[1].split("}", 1)[0]
    assert "padding: 0 24px;" in preview_frame_css
    assert "column-gap: 10px;" in preview_frame_css
    assert "row-gap: 20px;" in preview_frame_css
    assert 'scale(var(--duel-preview-scale))' in index
    assert 'window.addEventListener("resize", syncDuelPreviewStreamFrame);' in index
    assert 'document.body.appendChild(controls);' in index
    assert 'left: calc(var(--duel-preview-frame-right) + 12px);' in index
    assert 'moveDuelPreviewControlsOutsideFrame();' in index
    assert "--arena-purple-900: #4a3e8a;" in index
    assert "--arena-purple-700: #8d6fde;" in index
    assert "--arena-orange-900: #f0883e;" in index
    assert "--arena-orange-700: #ffa857;" in index
    assert "--arena-black: #100f12;" in index
    stream_surface_css = index.split("html.duel-preview #container.duel-layout-active {", 2)[-1].split("}", 1)[0]
    assert "background: var(--arena-surface-2);" in stream_surface_css
    outer_panel_css = index.split("html.duel-preview #duel-pov-grid.duel-active .duel-pov-card,", 1)[1].split("}", 1)[0]
    assert "border: 0;" in outer_panel_css
    assert "background: transparent;" in outer_panel_css
    assert "box-shadow: none;" in outer_panel_css
    assert 'font-family: "Saira Condensed";' in index
    assert '--arena-duel-font: "Saira Condensed", "Arial Narrow", sans-serif;' in index
    assert "#container.duel-layout-active *" in index
    assert "font-family: var(--arena-duel-font) !important;" in index
    assert "font: 800 clamp(30px, 2.7vw, 42px)/0.95" in index
    assert "font: 700 16px/1.35" in index
    assert "font-size: clamp(42px, 3.8vw, 58px);" in index
    assert "font: 700 18px/1.25" in index
    assert "font: 800 13px/1" in index
    assert "#7b8b84" not in layout_svg
    assert "#d7e0d8" not in layout_svg
    assert "#65646e" in layout_svg
    assert "#d9cffa" in layout_svg
    assert '["fighting", "finished", "waiting", "disconnected"]' in index
    assert 'id="duel-tactical-map-image" src="assets/duel_room_layout.svg?v=stream-palette-20260731"' in index
    assert "image.hidden = false;" in index
    assert "if (duelPreviewRequestedState)" in initializer
    preview_branch = initializer.split("if (duelPreviewRequestedState)", 1)[1].split("}", 1)[0]
    assert "initializeDuelPreview(duelPreviewRequestedState);" in preview_branch
    assert "return;" in preview_branch


def test_duel_autostart_reuses_server_session_without_run_metadata() -> None:
    index = (REPO_ROOT / "src" / "index.html").read_text(encoding="utf-8-sig")
    function_body = index.split("function startDuelFromExistingRun()", 1)[1].split(
        "function commandTiming", 1
    )[0]

    assert "loadDuelSessionStateForLauncher()" in function_body
    assert "!metadataText ||" not in function_body
    assert "!sessionPayload ||" in function_body


def test_server_rejects_legacy_manual_identity_registration() -> None:
    handler = make_handler()

    with pytest.raises(server.DoomArenaError, match="automatic session detection"):
        handler.update_participant_ready_agent(
            {
                "participant_id": "player_1",
                "coding_assistant": "Codex",
                "model": "GPT-5",
            }
        )


def test_participant_ready_endpoint_returns_bad_request_for_manual_identity() -> None:
    handler = make_handler()
    handler.headers = {"Content-Type": "application/json"}
    handler.wfile = BytesIO()
    handler.read_body = lambda: json.dumps(
        {
            "participant_id": "player_1",
            "coding_assistant": "Codex",
            "model": "GPT-5",
            "ready_at_ms": 1,
            "status": "ready",
        }
    ).encode("utf-8")
    response_meta = {}
    handler.send_response = lambda response_status: response_meta.__setitem__("status", response_status)
    handler.send_header = lambda _name, _value: None
    handler.end_headers = lambda: None

    handler.write_participant_ready()

    body = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert response_meta["status"] == server.HTTPStatus.BAD_REQUEST
    assert "automatic session detection" in body["error"]


def test_server_locks_first_match_alias_and_reuses_it_later() -> None:
    handler = make_handler()
    automatic_identity = {
        "participant_id": "player_1",
        "agent_name": "Expense Goblin",
        "coding_assistant": "Codex",
        "model": "gpt-5.6-sol low fast",
        "identity_source": "codex_session",
    }

    first = handler.update_participant_ready_agent(automatic_identity)
    later = handler.update_participant_ready_agent(
        {
            key: value
            for key, value in automatic_identity.items()
            if key != "agent_name"
        }
    )

    assert first["agent_name"] == "Expense Goblin"
    assert first["agent_label"] == (
        "Expense Goblin, Codex, gpt-5.6-sol low fast"
    )
    assert later == first
    assert handler.server.participant_ready_agents["player_1"] == first["agent_label"]

    with pytest.raises(server.DoomArenaError, match="locked"):
        handler.update_participant_ready_agent(
            {
                **automatic_identity,
                "agent_name": "Rename Menace",
            }
        )


def test_server_accepts_explicit_unavailable_identity_without_blocking_ready() -> None:
    handler = make_handler()

    identity = handler.update_participant_ready_agent(
        {
            "participant_id": "player_1",
            "agent_name": "Budget Falcon",
            "coding_assistant": "Undetected assistant",
            "model": "Model unavailable",
            "identity_source": "unavailable",
        }
    )

    assert identity["agent_name"] == "Budget Falcon"
    assert identity["agent_label"] == (
        "Budget Falcon, Undetected assistant, Model unavailable"
    )


def test_restart_duel_session_resets_round_and_alias_lock() -> None:
    handler = make_handler()
    handler.server.duel_session_id = "session_restart"
    handler.server.duel_total_rounds = 5
    handler.server.duel_current_round = 4
    handler.server.participant_agent_names = {
        "player_1": "Budget Falcon",
        "player_2": "Nacho Sheriff",
    }
    handler.server.duel_scenario_history = ["map_a", "map_b"]

    session_id, total_rounds, round_number = handler.restart_duel_session_state(3)

    assert session_id == "session_restart"
    assert total_rounds == 5
    assert round_number == 1
    assert handler.server.participant_agent_names == {}
    assert handler.server.duel_scenario_history == []


def test_server_requires_alias_when_session_has_none() -> None:
    handler = make_handler()

    with pytest.raises(server.DoomArenaError, match="agent_name"):
        handler.update_participant_ready_agent(
            {
                "participant_id": "player_1",
                "coding_assistant": "Codex",
                "model": "gpt-5.6-sol low fast",
                "identity_source": "codex_session",
            }
        )


def test_server_rejects_duplicate_alias_claimed_by_opponent() -> None:
    handler = make_handler()
    base_identity = {
        "agent_name": "Meeting Menace",
        "coding_assistant": "Codex",
        "model": "gpt-5.6-terra high fast",
        "identity_source": "codex_session",
    }

    handler.update_participant_ready_agent(
        {"participant_id": "player_1", **base_identity}
    )

    with pytest.raises(server.DoomArenaError, match="already claimed"):
        handler.update_participant_ready_agent(
            {
                "participant_id": "player_2",
                **base_identity,
                "agent_name": "meeting menace",
            }
        )

    assert "player_2" not in handler.server.participant_agent_names


def test_live_player_cards_and_results_omit_engine_accuracy() -> None:
    index = (REPO_ROOT / "src" / "index.html").read_text(encoding="utf-8-sig")

    assert 'id="duel-p1-shots"' not in index
    assert 'id="duel-p2-shots"' not in index
    assert "<tr><th>Hits / shots</th>" not in index
    assert "benchmarkAccuracy" not in index
    assert "<tr><th>Avg decision time</th>" in index
    assert "benchmarkDecisionTime" in index


def test_human_decision_feed_stitches_goal_and_reason_without_llm_call() -> None:
    index = (REPO_ROOT / "src" / "index.html").read_text(encoding="utf-8-sig")

    assert "Player 1 battle thoughts" not in index
    assert "Player 2 battle thoughts" not in index
    assert '<div class="duel-player-log">' in index
    assert '<details class="duel-player-log"' not in index
    assert 'return "Trying to " + objective + motivation' in index
    assert 'return "Tried to " + objective + motivation' in index
    assert 'return "Was trying to " + objective + motivation' in index
    assert 'var name = entry.agentName' not in index
    assert "Technical events (" not in index
    assert "duel-log-technical" not in index
    assert "Decision details" in index
    assert 'timingParts.push("Thought for " + friendlyLatency' in index
    assert 'context.textContent = "Latest decision"' in index
    assert "Earlier decisions (" not in index
    assert "duel-decision-history" not in index
    assert "if (!contentChanged) {" in index
    assert "return;" in index.split("if (!contentChanged) {", 1)[1].split("}", 1)[0]
    assert "var previousTechnicalOpen" in index
    assert "decisionTechnical.open = previousTechnicalOpen" in index
    assert 'quip.className = "duel-decision-quip"' not in index
    assert "stats.inferred_decision_turns.filter" in index
    assert '" · " + friendlyLatency(averageDecisionLatency + "ms") + " avg"' in index
    assert "decisionRows = applyCurrentExecutionToRows" in index
    assert "lines.push(decisionLine)" in index
    assert "left.issuedAtMs || 0" in index
    assert "if (rows.length > 0)" not in index
