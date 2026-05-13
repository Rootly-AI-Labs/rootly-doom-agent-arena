#!/usr/bin/env python3
"""player_2 control loop for Doom Arena Duel."""
import json
import sys
import time
import urllib.request
import urllib.error

SERVER_URL = "http://127.0.0.1:8001"
PARTICIPANT_ID = "player_2"
CONTROLLER_TOKEN = "PXEmO-8IsgqfMbSaJ70LDJ3Wm8OozMkF"

PARTICIPANT_COMMAND_HEADER = (
    "run_id\tscenario_id\tcommand_id\tissued_at_ms\texpires_at_ms\t"
    "participant_id\tforward\tstrafe\tturn\tattack\tuse\tduration_ms\n"
)
PARTICIPANT_COMMAND_KEYS = [
    "run_id", "scenario_id", "command_id", "issued_at_ms", "expires_at_ms",
    "participant_id", "forward", "strafe", "turn", "attack", "use", "duration_ms"
]


def now_ms():
    return int(time.time() * 1000)


def http_get(path):
    url = SERVER_URL + path
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8")


def http_post(path, body, content_type="text/tab-separated-values; charset=utf-8"):
    url = SERVER_URL + path
    req = urllib.request.Request(url, data=body.encode("utf-8") if isinstance(body, str) else body,
                                  headers={"Content-Type": content_type}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8")


def parse_state(text):
    lines = text.strip().split("\n")
    if not lines:
        return []
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        vals = line.split("\t")
        row = dict(zip(headers, vals))
        rows.append(row)
    return rows


def get_state():
    return parse_state(http_get("/api/arena/state"))


def get_match_phase(rows):
    for row in rows:
        if row.get("kind") == "match":
            return row.get("phase", ""), row.get("winner", ""), row.get("terminal_reason", "")
    return "", "", ""


def get_participant_row(rows, pid):
    for row in rows:
        if row.get("kind") == "participant" and row.get("entity_id") == pid:
            return row
    return {}


def get_current_commands():
    try:
        body = http_get("/api/arena/participant-commands")
        lines = body.strip().split("\n")
        if not lines:
            return []
        headers = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            vals = line.split("\t")
            rows.append(dict(zip(headers, vals)))
        return rows
    except Exception:
        return []


def set_participant_input(run_id, scenario_id, forward=0, strafe=0, turn=0, attack=False, use=False, duration_ms=750):
    issued = now_ms()
    command = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "command_id": f"{PARTICIPANT_ID}_cmd_{issued}",
        "issued_at_ms": str(issued),
        "expires_at_ms": str(issued + duration_ms),
        "participant_id": PARTICIPANT_ID,
        "forward": str(max(-1, min(1, forward))),
        "strafe": str(max(-1, min(1, strafe))),
        "turn": str(max(-1, min(1, turn))),
        "attack": "true" if attack else "false",
        "use": "false",
        "duration_ms": str(duration_ms),
    }
    # Read existing commands, filter out player_2, add new
    existing = get_current_commands()
    existing = [r for r in existing if r.get("participant_id") != PARTICIPANT_ID]
    existing.append(command)

    body = PARTICIPANT_COMMAND_HEADER
    for row in existing:
        body += "\t".join(row.get(k, "") for k in PARTICIPANT_COMMAND_KEYS) + "\n"
    http_post("/api/arena/participant-commands", body)
    return command


def decide_action(self_row, opp_row):
    """Return (forward, strafe, turn, attack, duration_ms) based on observation."""
    health = int(self_row.get("health", 100))
    opp_visible = self_row.get("line_of_sight", "0") == "1"
    try:
        opp_distance = float(self_row.get("distance_to_player", 9999))
    except ValueError:
        opp_distance = 9999
    try:
        rel_angle = float(self_row.get("relative_angle_to_player", 0))
    except ValueError:
        rel_angle = 0

    forward = 0
    strafe = 0
    turn = 0
    attack = False
    duration_ms = 750

    if not opp_visible:
        # Search by rotating
        turn = 1
        forward = 0
        attack = False
    elif -8 <= rel_angle <= 8:
        # Lined up - shoot
        attack = True
        forward = 0
        strafe = 0
        turn = 0
    elif rel_angle > 0:
        # Turn right
        turn = 1
        if opp_distance > 400:
            forward = 1
        attack = opp_distance < 600
    else:
        # Turn left
        turn = -1
        if opp_distance > 400:
            forward = 1
        attack = opp_distance < 600

    # If health low, keep strafing
    if health < 50:
        if strafe == 0:
            strafe = 1 if (now_ms() // 1000) % 2 == 0 else -1

    return forward, strafe, turn, attack, duration_ms


def main():
    print(f"[player_2] Starting control loop", flush=True)
    step = 0
    strafe_toggle = 1

    while True:
        try:
            rows = get_state()
        except Exception as e:
            print(f"[player_2] state fetch error: {e}", flush=True)
            time.sleep(0.5)
            continue

        phase, winner, reason = get_match_phase(rows)
        print(f"[player_2] step={step} phase={phase} winner={winner}", flush=True)

        if phase == "finished":
            print(f"[player_2] Match finished. Winner: {winner}. Reason: {reason}", flush=True)
            break

        match_row = next((r for r in rows if r.get("kind") == "match"), {})
        run_id = match_row.get("run_id", "")
        scenario_id = match_row.get("scenario_id", "duel_e1m8")

        self_row = get_participant_row(rows, PARTICIPANT_ID)
        opp_row = get_participant_row(rows, "player_1")

        if not self_row:
            print(f"[player_2] no self observation, waiting...", flush=True)
            time.sleep(0.5)
            continue

        health = int(self_row.get("health", 100))
        opp_visible = self_row.get("line_of_sight", "0") == "1"
        try:
            rel_angle = float(self_row.get("relative_angle_to_player", 0))
        except ValueError:
            rel_angle = 0
        try:
            opp_distance = float(self_row.get("distance_to_player", 9999))
        except ValueError:
            opp_distance = 9999

        forward, strafe, turn, attack, duration_ms = decide_action(self_row, opp_row)

        # Alternate strafe when close
        if opp_visible and opp_distance < 300:
            strafe = strafe_toggle
            strafe_toggle *= -1

        print(f"[player_2] health={health} vis={opp_visible} dist={opp_distance:.0f} angle={rel_angle:.1f} "
              f"-> fwd={forward} strafe={strafe} turn={turn} atk={attack}", flush=True)

        try:
            set_participant_input(run_id, scenario_id, forward, strafe, turn, attack, duration_ms=duration_ms)
        except Exception as e:
            print(f"[player_2] input error: {e}", flush=True)

        step += 1
        time.sleep(0.75)

    print("[player_2] Loop ended.", flush=True)


if __name__ == "__main__":
    main()
