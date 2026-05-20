#!/usr/bin/env python3
"""Compile and smoke-test Doom Arena participant autopilot decisions."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


HARNESS_C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "arena_participant_autopilot.h"

static arena_participant_intent_t make_intent(const char *intent_name)
{
    arena_participant_intent_t intent;

    memset(&intent, 0, sizeof(intent));
    intent.active = 1;
    intent.valid = 1;
    intent.participant = ARENA_PARTICIPANT_PLAYER_1;
    intent.target_participant = ARENA_PARTICIPANT_PLAYER_2;
    intent.preferred_distance = 600;
    intent.aggression = 0.5;
    strcpy(intent.intent_id, "intent_test");
    strcpy(intent.intent, intent_name);
    strcpy(intent.style, "balanced");
    strcpy(intent.strafe_direction, "auto");
    strcpy(intent.movement_bias, "direct");
    strcpy(intent.fire_policy, "only_when_aligned");
    strcpy(intent.distance_policy, "maintain");
    strcpy(intent.los_lost_action, "sweep");
    strcpy(intent.stuck_recovery_strategy, "default");
    strcpy(intent.turn_policy, "auto");
    strcpy(intent.navigation_target, "opponent");
    strcpy(intent.fire_mode, "auto");
    strcpy(intent.status, "valid");
    return intent;
}

static arena_participant_autopilot_input_t base_input(const char *intent_name)
{
    arena_participant_autopilot_input_t input;

    memset(&input, 0, sizeof(input));
    input.participant = ARENA_PARTICIPANT_PLAYER_1;
    input.intent = make_intent(intent_name);
    input.self_ammo = 50;
    input.self_health = 100;
    input.opponent_health = 100;
    input.distance = 700;
    input.relative_angle = 0;
    input.line_of_sight = 1;
    input.tick = 0;
    return input;
}

static void assert_unit_values(arena_participant_autopilot_command_t command, const char *label);

static void expect_exact_command(const char *label,
                                 arena_participant_autopilot_command_t command,
                                 int forward,
                                 int strafe,
                                 int turn,
                                 int attack)
{
    if (command.forward != forward
        || command.strafe != strafe
        || command.turn != turn
        || command.attack != attack)
    {
        fprintf(stderr,
                "FAIL: %s expected f=%d s=%d t=%d attack=%d, got f=%d s=%d t=%d attack=%d action=%s reason=%s\n",
                label,
                forward,
                strafe,
                turn,
                attack,
                command.forward,
                command.strafe,
                command.turn,
                command.attack,
                command.action,
                command.reason);
        exit(1);
    }
    assert_unit_values(command, label);
    printf("ok %s -> f=%d s=%d t=%d attack=%d action=%s reason=%s\n",
           label,
           command.forward,
           command.strafe,
           command.turn,
           command.attack,
           command.action,
           command.reason);
}

static void assert_unit_values(arena_participant_autopilot_command_t command, const char *label)
{
    if (command.forward < -1 || command.forward > 1
        || command.strafe < -1 || command.strafe > 1
        || command.turn < -1 || command.turn > 1)
    {
        fprintf(stderr, "FAIL: %s produced out-of-range values f=%d s=%d t=%d\n",
                label,
                command.forward,
                command.strafe,
                command.turn);
        exit(1);
    }
}

static void expect_command(const char *label,
                           arena_participant_autopilot_command_t command,
                           int active,
                           int forward,
                           int strafe_any,
                           int turn,
                           int attack,
                           int stuck_recovery)
{
    if (command.active != active)
    {
        fprintf(stderr, "FAIL: %s expected active=%d got %d (%s)\n",
                label, active, command.active, command.reason);
        exit(1);
    }
    if (command.forward != forward)
    {
        fprintf(stderr, "FAIL: %s expected forward=%d got %d\n", label, forward, command.forward);
        exit(1);
    }
    if (!strafe_any && command.strafe != 0)
    {
        fprintf(stderr, "FAIL: %s expected strafe=0 got %d\n", label, command.strafe);
        exit(1);
    }
    if (strafe_any && command.strafe == 0)
    {
        fprintf(stderr, "FAIL: %s expected nonzero strafe\n", label);
        exit(1);
    }
    if (command.turn != turn)
    {
        fprintf(stderr, "FAIL: %s expected turn=%d got %d\n", label, turn, command.turn);
        exit(1);
    }
    if (command.attack != attack)
    {
        fprintf(stderr, "FAIL: %s expected attack=%d got %d\n", label, attack, command.attack);
        exit(1);
    }
    if (command.stuck_recovery != stuck_recovery)
    {
        fprintf(stderr, "FAIL: %s expected stuck_recovery=%d got %d\n",
                label, stuck_recovery, command.stuck_recovery);
        exit(1);
    }
    assert_unit_values(command, label);
    printf("ok %s -> active=%d f=%d s=%d t=%d attack=%d action=%s reason=%s\n",
           label,
           command.active,
           command.forward,
           command.strafe,
           command.turn,
           command.attack,
           command.action,
           command.reason);
}

int main(void)
{
    arena_participant_autopilot_input_t input;
    arena_participant_autopilot_command_t command;

    input = base_input("engage_opponent");
    input.intent.active = 0;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("no active intent returns fallback", command, 0, 0, 0, 0, 0, 0);

    input = base_input("hold");
    input.relative_angle = 0;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("hold aligned visible attacks", command, 1, 0, 0, 0, 1, 0);

    input = base_input("hold");
    input.relative_angle = 30;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("hold not aligned turns only", command, 1, 0, 0, 1, 0, 0);

    input = base_input("search");
    input.line_of_sight = 0;
    input.tick = 0;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("search turns", command, 1, 1, 0, 1, 0, 0);

    input = base_input("engage_opponent");
    input.distance = 1200;
    input.relative_angle = -20;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("engage far moves forward", command, 1, 1, 0, -1, 0, 0);

    input = base_input("engage_opponent");
    input.distance = 500;
    input.tick = 0;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("engage close strafes and stops", command, 1, 0, 1, 0, 1, 0);

    input = base_input("strafe_attack");
    input.distance = 500;
    input.relative_angle = 0;
    input.tick = 0;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("strafe_attack aligned strafes and attacks", command, 1, 0, 1, 0, 1, 0);

    input = base_input("strafe_attack");
    input.distance = 500;
    input.relative_angle = 24;
    input.tick = 0;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("strafe_attack unaligned does not attack", command, 1, 0, 1, 1, 0, 0);

    input = base_input("strafe_attack");
    input.distance = 500;
    strcpy(input.intent.strafe_direction, "left");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("strafe_direction left produces left strafe", command, 0, -1, 0, 1);

    input = base_input("strafe_attack");
    input.distance = 500;
    strcpy(input.intent.strafe_direction, "right");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("strafe_direction right produces right strafe", command, 0, 1, 0, 1);

    input = base_input("hold");
    strcpy(input.intent.fire_policy, "hold_fire");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("fire_policy hold_fire prevents attack", command, 0, 0, 0, 0);

    input = base_input("hold");
    input.relative_angle = 20;
    strcpy(input.intent.fire_policy, "suppressive");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("fire_policy suppressive uses looser aim threshold", command, 0, 0, 1, 1);

    input = base_input("hold");
    input.relative_angle = 0;
    input.tick = 10;
    strcpy(input.intent.fire_policy, "burst_when_aligned");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("fire_policy burst_when_aligned cools down", command, 0, 0, 0, 0);

    input = base_input("hold");
    input.relative_angle = 12;
    input.intent.aim_tolerance = 15;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("aim_tolerance loosens only_when_aligned threshold", command, 0, 0, 1, 1);

    input = base_input("hold");
    input.relative_angle = 6;
    input.intent.min_fire_alignment = 5;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("min_fire_alignment tightens fire threshold", command, 0, 0, 0, 0);

    input = base_input("hold");
    input.relative_angle = 0;
    input.tick = 1;
    strcpy(input.intent.fire_mode, "single_shot");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("fire_mode single_shot pulses attack timing", command, 0, 0, 0, 0);

    input = base_input("strafe_attack");
    input.distance = 300;
    strcpy(input.intent.distance_policy, "kite");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("distance_policy kite backs away when close", command, 1, -1, 1, 0, 1, 0);

    input = base_input("engage_opponent");
    input.distance = 800;
    strcpy(input.intent.movement_bias, "evasive");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("movement_bias evasive reduces direct forward movement", command, 1, 0, 1, 0, 1, 0);

    input = base_input("search");
    input.line_of_sight = 0;
    strcpy(input.intent.los_lost_action, "turn_left");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("los_lost_action turn_left controls search", command, 0, 0, -1, 0);

    input = base_input("hold");
    input.relative_angle = 0;
    strcpy(input.intent.turn_policy, "sweep_left");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("turn_policy sweep_left controls turning", command, 0, 0, -1, 1);

    input = base_input("engage_opponent");
    strcpy(input.intent.navigation_target, "left_lane");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("navigation_target left_lane adds left strafe", command, 1, 1, 1, 0, 1, 0);

    input = base_input("engage_opponent");
    strcpy(input.intent.movement_primitive, "retreat");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_exact_command("movement_primitive retreat overrides engage movement", command, -1, 0, 0, 1);

    input = base_input("engage_opponent");
    input.distance = 200;
    input.intent.retreat_if_closer_than = 300;
    strcpy(input.intent.movement_primitive, "advance");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("strict spacing overrides unsafe movement primitive", command, 1, -1, 1, 0, 1, 0);

    input = base_input("engage_opponent");
    input.stuck_ticks = 9;
    strcpy(input.intent.stuck_recovery_strategy, "turn_right");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("stuck_recovery_strategy turn_right overrides default", command, 1, 0, 0, 1, 1, 1);

    input = base_input("strafe_attack");
    input.distance = 80;
    input.stuck_ticks = 9;
    input.relative_angle = 0;
    strcpy(input.intent.stuck_recovery_strategy, "strafe_out");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("point-blank stuck recovery suppresses attack to separate", command, 1, 0, 1, 0, 0, 1);

    input = base_input("strafe_attack");
    input.distance = 800;
    input.intent.max_distance = 700;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("max_distance requests push when too far", command, 1, 1, 1, 0, 1, 0);

    input = base_input("engage_opponent");
    input.line_of_sight = 0;
    input.distance = 1200;
    strcpy(input.intent.replan_if, "lost_los,target_far");
    command = ArenaParticipantAutopilot_Decide(&input);
    if (!command.replan_recommended
        || strcmp(command.replan_reasons, "lost_los,target_far"))
    {
        fprintf(stderr,
                "FAIL: replan_if lost_los/target_far expected reasons, got recommended=%d reasons=%s\n",
                command.replan_recommended,
                command.replan_reasons);
        exit(1);
    }
    printf("ok replan_if lost_los,target_far exports recommendation -> %s\n",
           command.replan_reasons);

    input = base_input("engage_opponent");
    input.stuck_ticks = 9;
    input.relative_angle = 0;
    strcpy(input.intent.replan_if, "stuck");
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("stuck recovery overrides movement", command, 1, -1, 1, -1, 1, 1);
    if (!command.replan_recommended || strcmp(command.replan_reasons, "stuck"))
    {
        fprintf(stderr,
                "FAIL: replan_if stuck expected stuck reason, got recommended=%d reasons=%s\n",
                command.replan_recommended,
                command.replan_reasons);
        exit(1);
    }
    printf("ok replan_if stuck exports recommendation -> %s\n", command.replan_reasons);

    input = base_input("hold");
    input.phase_finished = 1;
    command = ArenaParticipantAutopilot_Decide(&input);
    expect_command("phase finished no-op", command, 1, 0, 0, 0, 0, 0);

    input = base_input("hold");
    input.relative_angle = 725;
    command = ArenaParticipantAutopilot_Decide(&input);
    assert_unit_values(command, "normalized large angle output values clamped");
    printf("ok normalized large angle output values clamped -> turn=%d aim_error=%d\n",
           command.turn,
           command.aim_error);

    printf("participant autopilot smoke test passed\n");
    return 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test participant autopilot C code.")
    parser.add_argument("--gcc", default="gcc")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="doom_arena_autopilot_") as tmp:
        tmp_path = Path(tmp)
        harness_path = tmp_path / "autopilot_harness.c"
        exe_path = tmp_path / "autopilot_harness.exe"
        harness_path.write_text(HARNESS_C, encoding="utf-8")
        command = [
            args.gcc,
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-I",
            str(REPO_ROOT),
            "-I",
            str(REPO_ROOT / "src"),
            "-I",
            str(REPO_ROOT / "src" / "doom"),
            str(REPO_ROOT / "src" / "doom" / "arena_participant_autopilot.c"),
            str(harness_path),
            "-o",
            str(exe_path),
        ]
        subprocess.run(command, check=True, cwd=tmp_path)
        result = subprocess.run(
            [str(exe_path)],
            check=True,
            cwd=tmp_path,
            text=True,
            capture_output=True,
        )
        print(result.stdout, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
