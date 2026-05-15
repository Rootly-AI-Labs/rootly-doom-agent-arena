#!/usr/bin/env python3
"""Compile and smoke-test the Doom-side participant intent parser."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


HARNESS_C = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "arena_participant_intents.h"

static int fake_now_ms = 0;

int I_GetTimeMS(void)
{
    return fake_now_ms;
}

const char *Arena_RunId(void)
{
    return "run_test";
}

const char *Arena_ScenarioId(void)
{
    return "duel_e1m8";
}

static void fail(const char *message)
{
    fprintf(stderr, "FAIL: %s\n", message);
    exit(1);
}

static void write_intents(const char *rows)
{
    FILE *file;

    file = fopen("arena_participant_intents.local.tsv", "wb");
    if (file == NULL)
    {
        fail("could not write intent TSV");
    }

    fputs("run_id\tscenario_id\tintent_id\tissued_at_ms\texpires_at_ms\tparticipant_id\tintent\tstyle\ttarget_id\tpreferred_distance\taggression\tduration_ms\tstrafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\taim_tolerance\tfire_burst_ms\tmin_fire_alignment\tmin_distance\tmax_distance\tretreat_if_closer_than\tpush_if_farther_than\tlos_lost_action\tstuck_recovery_strategy\tmovement_primitive\tturn_policy\tnavigation_target\tfire_mode\n", file);
    if (rows != NULL)
    {
        fputs(rows, file);
    }
    fclose(file);
}

static void remove_intents(void)
{
    remove("arena_participant_intents.local.tsv");
}

static void expect_inactive(arena_participant_id_t participant, const char *status, const char *label)
{
    arena_participant_intent_t intent;

    intent = ArenaParticipantIntent_Get(participant);
    if (intent.active)
    {
        fprintf(stderr, "FAIL: %s expected inactive, got active %s\n", label, intent.intent);
        exit(1);
    }
    if (strcmp(intent.status, status))
    {
        fprintf(stderr, "FAIL: %s expected status %s, got %s (%s)\n", label, status, intent.status, intent.reason);
        exit(1);
    }
    printf("ok %s -> inactive status=%s reason=%s\n", label, intent.status, intent.reason);
}

static void expect_active(arena_participant_id_t participant, const char *intent_name, const char *style, const char *label)
{
    arena_participant_intent_t intent;

    intent = ArenaParticipantIntent_Get(participant);
    if (!intent.active)
    {
        fprintf(stderr, "FAIL: %s expected active, got status %s (%s)\n", label, intent.status, intent.reason);
        exit(1);
    }
    if (strcmp(intent.intent, intent_name) || strcmp(intent.style, style))
    {
        fprintf(stderr, "FAIL: %s expected %s/%s, got %s/%s\n", label, intent_name, style, intent.intent, intent.style);
        exit(1);
    }
    printf("ok %s -> active intent=%s style=%s target=%d\n", label, intent.intent, intent.style, intent.target_participant);
}

static void expect_active_status(arena_participant_id_t participant,
                                 const char *intent_name,
                                 const char *style,
                                 const char *status,
                                 const char *label)
{
    arena_participant_intent_t intent;

    intent = ArenaParticipantIntent_Get(participant);
    if (!intent.active)
    {
        fprintf(stderr, "FAIL: %s expected active, got status %s (%s)\n", label, intent.status, intent.reason);
        exit(1);
    }
    if (strcmp(intent.intent, intent_name) || strcmp(intent.style, style))
    {
        fprintf(stderr, "FAIL: %s expected %s/%s, got %s/%s\n", label, intent_name, style, intent.intent, intent.style);
        exit(1);
    }
    if (strcmp(intent.status, status))
    {
        fprintf(stderr, "FAIL: %s expected status %s, got %s (%s)\n", label, status, intent.status, intent.reason);
        exit(1);
    }
    printf("ok %s -> active status=%s intent=%s style=%s\n", label, intent.status, intent.intent, intent.style);
}

static void expect_tactical_fields(arena_participant_id_t participant,
                                   const char *strafe_direction,
                                   const char *movement_bias,
                                   const char *fire_policy,
                                   const char *distance_policy,
                                   const char *replan_if,
                                   int sequence_number,
                                   int decision_cadence_ms,
                                   const char *label)
{
    arena_participant_intent_t intent;

    intent = ArenaParticipantIntent_Get(participant);
    if (strcmp(intent.strafe_direction, strafe_direction)
        || strcmp(intent.movement_bias, movement_bias)
        || strcmp(intent.fire_policy, fire_policy)
        || strcmp(intent.distance_policy, distance_policy)
        || strcmp(intent.replan_if, replan_if)
        || intent.sequence_number != sequence_number
        || intent.decision_cadence_ms != decision_cadence_ms)
    {
        fprintf(stderr,
                "FAIL: %s expected tactical fields %s/%s/%s/%s/%s/%d/%d, got %s/%s/%s/%s/%s/%d/%d\n",
                label,
                strafe_direction,
                movement_bias,
                fire_policy,
                distance_policy,
                replan_if,
                sequence_number,
                decision_cadence_ms,
                intent.strafe_direction,
                intent.movement_bias,
                intent.fire_policy,
                intent.distance_policy,
                intent.replan_if,
                intent.sequence_number,
                intent.decision_cadence_ms);
        exit(1);
    }
    printf("ok %s -> tactical fields parsed\n", label);
}

static void expect_extended_fields(arena_participant_id_t participant,
                                   int aim_tolerance,
                                   int fire_burst_ms,
                                   int min_fire_alignment,
                                   int min_distance,
                                   int max_distance,
                                   int retreat_if_closer_than,
                                   int push_if_farther_than,
                                   const char *los_lost_action,
                                   const char *stuck_recovery_strategy,
                                   const char *movement_primitive,
                                   const char *turn_policy,
                                   const char *navigation_target,
                                   const char *fire_mode,
                                   const char *label)
{
    arena_participant_intent_t intent;

    intent = ArenaParticipantIntent_Get(participant);
    if (intent.aim_tolerance != aim_tolerance
        || intent.fire_burst_ms != fire_burst_ms
        || intent.min_fire_alignment != min_fire_alignment
        || intent.min_distance != min_distance
        || intent.max_distance != max_distance
        || intent.retreat_if_closer_than != retreat_if_closer_than
        || intent.push_if_farther_than != push_if_farther_than
        || strcmp(intent.los_lost_action, los_lost_action)
        || strcmp(intent.stuck_recovery_strategy, stuck_recovery_strategy)
        || strcmp(intent.movement_primitive, movement_primitive)
        || strcmp(intent.turn_policy, turn_policy)
        || strcmp(intent.navigation_target, navigation_target)
        || strcmp(intent.fire_mode, fire_mode))
    {
        fprintf(stderr, "FAIL: %s extended fields mismatch\n", label);
        exit(1);
    }
    printf("ok %s -> extended fields parsed\n", label);
}

int main(void)
{
    ArenaParticipantIntent_Init();

    remove_intents();
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "missing", "missing file player_1");
    expect_inactive(ARENA_PARTICIPANT_PLAYER_2, "missing", "missing file player_2");

    write_intents("");
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "missing", "header-only player_1");
    expect_inactive(ARENA_PARTICIPANT_PLAYER_2, "missing", "header-only player_2");

    write_intents(
        "run_test\tduel_e1m8\tp1_1000\t1000\t3500\tplayer_1\tengage_opponent\tbalanced\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 10;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "engage_opponent", "balanced", "valid player_1 intent");
    expect_tactical_fields(ARENA_PARTICIPANT_PLAYER_1,
                           "auto",
                           "direct",
                           "only_when_aligned",
                           "maintain",
                           "",
                           0,
                           0,
                           "legacy row defaults");
    expect_extended_fields(ARENA_PARTICIPANT_PLAYER_1,
                           0,
                           0,
                           0,
                           0,
                           0,
                           0,
                           0,
                           "sweep",
                           "default",
                           "",
                           "auto",
                           "opponent",
                           "auto",
                           "legacy extended defaults");

    write_intents(
        "run_test\tduel_e1m8\tp1_extended\t1100\t3600\tplayer_1\tstrafe_attack\taggressive\tplayer_2\t500\t0.8\t2500\tswitch_if_hit\tcircle\tburst_when_aligned\tkite\tlost_los,stuck\t4\t750\t12\t280\t7\t300\t900\t250\t1000\tadvance_last_seen\tstrafe_out\tcircle_right\tturn_to_enemy\topponent\tburst\n"
    );
    fake_now_ms = 15;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "strafe_attack", "aggressive", "valid extended player_1 intent");
    expect_tactical_fields(ARENA_PARTICIPANT_PLAYER_1,
                           "switch_if_hit",
                           "circle",
                           "burst_when_aligned",
                           "kite",
                           "lost_los,stuck",
                           4,
                           750,
                           "extended row fields");
    expect_extended_fields(ARENA_PARTICIPANT_PLAYER_1,
                           12,
                           280,
                           7,
                           300,
                           900,
                           250,
                           1000,
                           "advance_last_seen",
                           "strafe_out",
                           "circle_right",
                           "turn_to_enemy",
                           "opponent",
                           "burst",
                           "extended movement control fields");

    write_intents(
        "run_test\tduel_e1m8\tp1_1000\t1000\t3500\tplayer_1\tengage_opponent\tbalanced\tplayer_2\t600\t0.5\t2500\n"
        "run_test\tduel_e1m8\tp2_1200\t1200\t3700\tplayer_2\tstrafe_attack\taggressive\tplayer_1\t500\t0.8\t2500\n"
    );
    fake_now_ms = 20;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_2, "strafe_attack", "aggressive", "valid player_2 intent");

    write_intents(
        "run_test\tduel_e1m8\tp1_invalid_intent\t2000\t4500\tplayer_1\tteleport_attack\tbalanced\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 30;
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "invalid", "invalid intent");

    write_intents(
        "run_test\tduel_e1m8\tp1_invalid_style\t3000\t5500\tplayer_1\thold\treckless\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 40;
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "invalid", "invalid style");

    write_intents(
        "run_test\tduel_e1m8\tp1_invalid_tactical\t3500\t6000\tplayer_1\thold\tcautious\tplayer_2\t600\t0.5\t2500\tsideways\tdirect\tonly_when_aligned\tmaintain\t\t\t750\n"
    );
    fake_now_ms = 45;
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "invalid", "invalid tactical enum");

    write_intents(
        "run_test\tduel_e1m8\tp1_invalid_cadence\t3600\t6100\tplayer_1\thold\tcautious\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t\t0\n"
    );
    fake_now_ms = 46;
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "invalid", "invalid cadence");

    write_intents(
        "run_test\tduel_e1m8\tp1_invalid_movement_primitive\t3700\t6200\tplayer_1\thold\tcautious\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t\t750\t\t\t\t\t\t\t\tsweep\tdefault\tteleport\n"
    );
    fake_now_ms = 47;
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "invalid", "invalid movement primitive");

    write_intents(
        "run_test\tduel_e1m8\tp1_wrong_target\t4000\t6500\tplayer_1\tsearch\tbalanced\tplayer_1\t600\t0.5\t2500\n"
    );
    fake_now_ms = 50;
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "invalid", "wrong target");

    write_intents(
        "run_test\tduel_e1m8\tp1_expired\t5000\t4000\tplayer_1\thold\tcautious\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 60;
    ArenaParticipantIntent_TickOrRefresh();
    expect_inactive(ARENA_PARTICIPANT_PLAYER_1, "expired", "expired intent");

    write_intents(
        "run_test\tduel_e1m8\tp1_newer\t6000\t8500\tplayer_1\tsearch\tbalanced\tplayer_2\t600\t0.5\t2500\n"
        "run_test\tduel_e1m8\tp1_older\t5900\t8400\tplayer_1\tengage_opponent\tbalanced\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 70;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "search", "balanced", "newest row wins");

    ArenaParticipantIntent_Init();
    write_intents(
        "run_test\tduel_e1m8\tp1_seq_lower_newer\t9100\t11600\tplayer_1\tsearch\tbalanced\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t2\t750\n"
        "run_test\tduel_e1m8\tp1_seq_higher_older\t9000\t11500\tplayer_1\tstrafe_attack\taggressive\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t5\t750\n"
    );
    fake_now_ms = 90;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "strafe_attack", "aggressive", "higher sequence wins over newer issued_at");
    expect_tactical_fields(ARENA_PARTICIPANT_PLAYER_1,
                           "auto",
                           "direct",
                           "only_when_aligned",
                           "maintain",
                           "",
                           5,
                           750,
                           "higher sequence parsed");

    write_intents(
        "run_test\tduel_e1m8\tp1_seq_lower_later\t9200\t11700\tplayer_1\tsearch\tbalanced\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t4\t750\n"
    );
    fake_now_ms = 100;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "strafe_attack", "aggressive", "lower sequence cannot override active higher sequence");

    ArenaParticipantIntent_Init();
    write_intents(
        "run_test\tduel_e1m8\tp1_seq_high_expired\t10000\t9000\tplayer_1\tstrafe_attack\taggressive\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t99\t750\n"
        "run_test\tduel_e1m8\tp1_seq_low_valid\t9300\t11800\tplayer_1\thold\tcautious\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t1\t750\n"
    );
    fake_now_ms = 110;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "hold", "cautious", "expired high sequence does not reactivate");

    ArenaParticipantIntent_Init();
    write_intents(
        "run_test\tduel_e1m8\tp1_seq_tie_older\t11000\t13500\tplayer_1\thold\tcautious\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t7\t750\n"
        "run_test\tduel_e1m8\tp1_seq_tie_newer\t11100\t13600\tplayer_1\tsearch\tbalanced\tplayer_2\t600\t0.5\t2500\tauto\tdirect\tonly_when_aligned\tmaintain\t\t7\t750\n"
    );
    fake_now_ms = 120;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "search", "balanced", "tied sequence falls back to issued_at freshness");

    ArenaParticipantIntent_Init();
    write_intents(
        "run_test\tduel_e1m8\tp1_newer_again\t6000\t8500\tplayer_1\tsearch\tbalanced\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 125;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "search", "balanced", "newer row setup before older stale check");

    write_intents(
        "run_test\tduel_e1m8\tp1_older\t5900\t8400\tplayer_1\tengage_opponent\tbalanced\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 80;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "search", "balanced", "older intent ignored while newer intent remains active");

    write_intents(
        "run_test\tduel_e1m8\tp1_expire_local\t7000\t9500\tplayer_1\tsearch\tbalanced\tplayer_2\t600\t0.5\t2500\n"
    );
    fake_now_ms = 100;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "search", "balanced", "local expiry setup");
    fake_now_ms = 2701;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active(ARENA_PARTICIPANT_PLAYER_1, "search", "balanced", "local duration grace");
    fake_now_ms = 4601;
    ArenaParticipantIntent_TickOrRefresh();
    expect_active_status(ARENA_PARTICIPANT_PLAYER_1, "search", "balanced", "stale", "local duration expiry sticks to last MCP intent");

    printf("participant intent parser smoke test passed\n");
    return 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test participant intent parser C code.")
    parser.add_argument("--gcc", default="gcc")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="doom_arena_intent_parser_") as tmp:
        tmp_path = Path(tmp)
        harness_path = tmp_path / "intent_parser_harness.c"
        exe_path = tmp_path / "intent_parser_harness.exe"
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
            str(REPO_ROOT / "src" / "doom" / "arena_participant_intents.c"),
            str(harness_path),
            "-o",
            str(exe_path),
        ]
        subprocess.run(command, check=True, cwd=tmp_path)
        env = os.environ.copy()
        result = subprocess.run(
            [str(exe_path)],
            check=True,
            cwd=tmp_path,
            text=True,
            capture_output=True,
            env=env,
        )
        print(result.stdout, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
