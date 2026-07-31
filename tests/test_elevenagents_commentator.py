import json
import shutil
import subprocess
from pathlib import Path

import doom_arena_server as server

from tests.test_duel_regressions import make_handler


REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: dict):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


def test_fetch_elevenlabs_signed_url_uses_server_key_without_leaking_it(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["key"] = request.headers["Xi-api-key"]
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "signed_url": (
                    "wss://api.elevenlabs.io/v1/convai/conversation"
                    "?agent_id=agent_test&conversation_signature=temporary"
                )
            }
        )

    monkeypatch.setattr(server, "urlopen", fake_urlopen)

    signed_url = server.fetch_elevenlabs_signed_url("secret-key", "agent_test")

    assert signed_url.startswith("wss://api.elevenlabs.io/")
    assert "agent_id=agent_test" in captured["url"]
    assert captured["key"] == "secret-key"
    assert captured["timeout"] == server.ELEVENLABS_REQUEST_TIMEOUT_SECONDS
    assert "secret-key" not in signed_url


def test_fetch_elevenlabs_signed_url_rejects_untrusted_host(monkeypatch):
    monkeypatch.setattr(
        server,
        "urlopen",
        lambda _request, timeout: FakeResponse(
            {"signed_url": "wss://attacker.example/steal"}
        ),
    )

    try:
        server.fetch_elevenlabs_signed_url("secret-key", "agent_test")
    except ValueError as exc:
        assert "invalid signed WebSocket URL" in str(exc)
    else:
        raise AssertionError("untrusted ElevenAgents URL was accepted")


def test_commentator_config_reports_only_missing_variable_names(monkeypatch):
    handler = make_handler()
    response = {}
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret-key")
    monkeypatch.delenv("ELEVENLABS_AGENT_ID", raising=False)
    handler.write_json = lambda status, payload: response.update(
        {"status": status, "payload": payload}
    )

    handler.read_commentator_config()

    assert response["status"] == server.HTTPStatus.OK
    assert response["payload"]["configured"] is False
    assert response["payload"]["missing"] == ["ELEVENLABS_AGENT_ID"]
    assert "secret-key" not in json.dumps(response)


def test_signed_url_endpoint_never_calls_upstream_when_unconfigured(monkeypatch):
    handler = make_handler()
    response = {}
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_AGENT_ID", raising=False)
    monkeypatch.setattr(
        server,
        "fetch_elevenlabs_signed_url",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected upstream call")),
    )
    handler.write_json = lambda status, payload: response.update(
        {"status": status, "payload": payload}
    )

    handler.read_commentator_signed_url()

    assert response["status"] == server.HTTPStatus.SERVICE_UNAVAILABLE
    assert response["payload"]["missing"] == [
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_AGENT_ID",
    ]


def test_commentary_director_sends_active_plans_without_raw_routes_or_coordinates():
    if not shutil.which("node"):
        return
    module_path = REPO_ROOT / "src" / "elevenagents-commentator.js"
    script = f"""
const assert = require('assert');
const api = require({json.dumps(str(module_path))});
const snapshot = api.buildSnapshot({{
  runId: 'run_test', phase: 'combat', elapsedSeconds: 47.9, round: 2,
  totalRounds: 5, scenario: 'Blind spawn', score: {{player_1: 1, player_2: 0}},
  player1Name: 'Invoice Badger', player2Name: 'Nacho Regrets',
  player1: {{health: '65', alive: '1', damage_dealt: '75', ready_weapon: '2',
    line_of_sight: '1', intent_id: 'intent_8', intent_status: 'active', x: '-512', y: '320'}},
  player2: {{health: '110', alive: '1', damage_dealt: '85', ready_weapon: '1',
    line_of_sight: '1', x: '320', y: '-64'}},
  pickups: {{player_1: {{health: 1, shotgun: 1}}, player_2: {{health: 0, shotgun: 0}}}},
  intentRows: [{{participant_id: 'player_1', intent_id: 'intent_8', sequence_number: '8',
    issued_at_ms: '45000', plan_objective: 'Push through center and engage',
    plan_engagement_policy: 'engage_if_visible',
    plan_reasoning: 'The shotgun is strongest at close range',
    plan_summary: 'Time for a very loud performance review',
    plan_route: 'B04;B05;B06', plan_route_cells: 'B04;B05;B06'}}]
}}, 50000);
assert.equal(snapshot.players.player_1.plan.objective, 'Push through center and engage');
assert.equal(snapshot.players.player_1.plan.decision_number, 8);
assert.equal(snapshot.players.player_1.plan.active_for_seconds, 5);
assert.deepEqual(snapshot.players.player_1.equipment, ['shotgun']);
assert.equal(snapshot.match.elapsed_seconds, 47);
const sameTactic = JSON.parse(JSON.stringify(snapshot));
sameTactic.players.player_1.plan.decision_number = 9;
assert.equal(api.chooseCue(snapshot, sameTactic), null);
const serialized = JSON.stringify(snapshot);
assert(!serialized.includes('B04'));
assert(!serialized.includes('-512'));
assert(!serialized.includes('controller_token'));
assert(!serialized.includes('plan_route'));
const publicPayload = JSON.stringify(api.publicSnapshot(snapshot));
assert(!publicPayload.includes('run_test'));
const waiting = JSON.parse(JSON.stringify(snapshot));
waiting.match.phase = 'waiting_for_agents';
const introCue = api.chooseCue(waiting, snapshot);
assert.equal(introCue.type, 'match_start');
assert(introCue.facts.includes('Open with: In the Rootly Doom Agent Areeennaaaa'));
assert(introCue.facts.includes('Player 1 is Invoice Badger'));
assert(introCue.facts.includes('Player 2 is Nacho Regrets'));
const introPayload = new api.Commentator({{}}).commentaryPayload(introCue, snapshot);
assert.equal(introPayload.delivery.maximum_words, 44);
assert.equal(api.cueDelayMs({{type: 'round_end'}}, 2500), 0);
assert.equal(api.cueDelayMs({{type: 'heavy_damage'}}, 2500), 350);
assert.equal(api.cueDelayMs({{type: 'plan_change'}}, 2500), 2200);
assert(introPayload.delivery.format.includes('PLAYERRR ONE'));
const finished = JSON.parse(JSON.stringify(snapshot));
finished.match.phase = 'finished';
finished.match.winner = 'player_1';
finished.match.terminal_reason = 'player_2_dead';
finished.players.player_2.health = 0;
const resultCue = api.chooseCue(snapshot, finished);
assert.equal(resultCue.type, 'round_end');
assert.equal(resultCue.actor, 'Invoice Badger');
assert(resultCue.facts.join(' ').includes('Nacho Regrets was eliminated'));
assert.equal(new api.Commentator({{}}).commentaryPayload(resultCue, finished).delivery.maximum_words, 14);
"""
    subprocess.run(["node", "-e", script], check=True, cwd=REPO_ROOT)


def test_spectator_loads_commentator_controls_and_external_director():
    index = (REPO_ROOT / "src" / "index.html").read_text(encoding="utf-8-sig")
    director = (REPO_ROOT / "src" / "elevenagents-commentator.js").read_text(
        encoding="utf-8"
    )

    assert 'src="elevenagents-commentator.js?v=20260731-low-latency-cadence"' in index
    assert 'id="arena-commentator-toggle"' in index
    assert 'id="arena-commentator-volume"' in index
    assert 'id="duel-commentator-toggle"' in index
    assert 'id="duel-commentator-caption"' in index
    assert 'id="duel-commentator-volume"' in index
    assert "updateElevenAgentsCommentator(" in index
    assert "/api/arena/commentator/signed-url" in index
    assert 'document.querySelectorAll("[data-commentator-toggle]")' in index
    assert 'type: "conversation_initiation_client_data"' in director
    assert 'href="elevenagents-test.html"' in index
    assert "Commentator.prototype.introduceMatch" in director
    assert "var arenaDuelStatePollMs = 500;" in index
    assert "window.setInterval(refreshDuelState, arenaDuelStatePollMs);" in index
    assert "var elevenAgentsCommentatorDesired = false;" in index
    assert 'syncElevenAgentsCommentatorControls("Shoutcaster enabled", true, false);' in index
    assert 'setElevenAgentsCommentatorStatus("Enabled by default — starts with benchmark", "ready");' in index
    assert "elevenAgentsCommentatorDesired &&" in index
    gate_call = index.index("presentDuelParticipantsBeforeStart()")
    runtime_start = index.index(
        'return startDuel({ reuseExistingSession: true });', gate_call
    )
    assert gate_call < runtime_start
    assert "Introduction complete. Starting benchmark" in index


def test_standalone_voice_test_bypasses_the_game_and_reports_each_stage():
    page = (REPO_ROOT / "src" / "elevenagents-test.html").read_text(encoding="utf-8")

    assert "Run voice test" in page
    assert "Browser audio" in page
    assert "Server configuration" in page
    assert "ElevenAgents connection" in page
    assert "Agent response" in page
    assert "Voice audio" in page
    assert "/api/arena/commentator/config" in page
    assert "/api/arena/commentator/signed-url" in page
    assert "Shoutcaster audio test successful" in page
    assert "elevenagents-commentator.js?v=20260731-low-latency-cadence" in page
    assert "browser autoplay policies" in page
    assert "Timed out after 15 seconds" in page
    assert "updateDuelDashboard" not in page


def test_commentator_sends_plain_test_messages_and_reports_scheduled_audio():
    if not shutil.which("node"):
        return
    module_path = REPO_ROOT / "src" / "elevenagents-commentator.js"
    script = f"""
const assert = require('assert');
global.WebSocket = {{OPEN: 1}};
global.atob = value => Buffer.from(value, 'base64').toString('binary');
global.window = {{setTimeout, clearTimeout}};
const api = require({json.dumps(str(module_path))});
let sent = null;
let audioEvent = null;
let source = null;
let flushed = 0;
const commentator = new api.Commentator({{onAudio: event => {{ audioEvent = event; }}}});
commentator.ready = true;
commentator.socket = {{readyState: 1, send: value => {{ sent = JSON.parse(value); }}}};
assert(commentator.send('user_message', 'Audio test'));
assert.deepEqual(sent, {{type: 'user_message', text: 'Audio test'}});
commentator.sampleRate = 16000;
commentator.audioContext = {{
  currentTime: 1,
  createBuffer: (_channels, length, rate) => ({{
    duration: length / rate,
    copyToChannel: () => {{}}
  }}),
  createBufferSource: () => (source = {{connect: () => {{}}, start: () => {{}}, onended: null}})
}};
commentator.gainNode = {{}};
commentator.speaking = true;
commentator.flushPendingCue = () => {{ flushed += 1; }};
commentator.queueAudio(Buffer.from([0, 0, 1, 0]).toString('base64'));
assert.equal(audioEvent.sample_rate, 16000);
assert.equal(audioEvent.sample_count, 2);
commentator.audioContext.currentTime = 2;
source.onended();
setTimeout(() => {{
  assert.equal(commentator.speaking, false);
  assert.equal(flushed, 1);
}}, 240);
"""
    subprocess.run(["node", "-e", script], check=True, cwd=REPO_ROOT)


def test_match_introduction_resolves_after_audio_and_suppresses_duplicate_start_cue():
    if not shutil.which("node"):
        return
    module_path = REPO_ROOT / "src" / "elevenagents-commentator.js"
    script = f"""
const assert = require('assert');
global.WebSocket = {{OPEN: 1}};
global.atob = value => Buffer.from(value, 'base64').toString('binary');
global.window = {{setTimeout, clearTimeout}};
const api = require({json.dumps(str(module_path))});

(async () => {{
  let sent = [];
  let source = null;
  const commentator = new api.Commentator({{}});
  commentator.enabled = true;
  commentator.ready = true;
  commentator.socket = {{
    readyState: 1,
    send: value => sent.push(JSON.parse(value))
  }};
  const introduction = commentator.introduceMatch({{
    runId: 'run_intro', round: 1, totalRounds: 3, scenario: 'Blind spawn',
    player1Name: 'Invoice Badger', player2Name: 'Nacho Regrets'
  }});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(sent.length, 1);
  const payload = JSON.parse(sent[0].text);
  assert.equal(payload.event.type, 'match_start');
  assert(payload.event.facts.includes('Open with: In the Rootly Doom Agent Areeennaaaa'));
  assert.equal(commentator.introducedRunId, '');

  commentator.sampleRate = 16000;
  commentator.audioContext = {{
    currentTime: 1,
    createBuffer: (_channels, length, rate) => ({{duration: length / rate, copyToChannel: () => {{}}}}),
    createBufferSource: () => (source = {{connect: () => {{}}, start: () => {{}}, onended: null}})
  }};
  commentator.gainNode = {{}};
  commentator.queueAudio(Buffer.from([0, 0, 1, 0]).toString('base64'));
  commentator.audioContext.currentTime = 2;
  source.onended();
  await introduction;
  assert.equal(commentator.introducedRunId, 'run_intro');

  const waiting = api.buildSnapshot({{
    runId: 'run_intro', phase: 'waiting_for_agents', player1Name: 'Invoice Badger',
    player2Name: 'Nacho Regrets', player1: {{}}, player2: {{}}
  }}, 1);
  commentator.lastSnapshot = waiting;
  sent = [];
  commentator.update({{
    runId: 'run_intro', phase: 'combat', player1Name: 'Invoice Badger',
    player2Name: 'Nacho Regrets', player1: {{}}, player2: {{}}
  }});
  assert(!sent.some(message => message.type === 'user_message'));
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""
    subprocess.run(["node", "-e", script], check=True, cwd=REPO_ROOT)
