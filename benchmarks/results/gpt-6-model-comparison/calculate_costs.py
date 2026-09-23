"""Reproduce standard-rate API-equivalent costs from local Codex rollouts.

Reads only the twelve rollouts indexed in README.md. Writes aggregate usage,
never prompts, tool arguments, controller tokens, or raw rollout content.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RATES = {"astra": (10, 1, 12.5, 50), "sol": (2, .2, 2.5, 10), "luna": (.1, .01, .125, .5)}
KEYS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")


def empty():
    return dict.fromkeys((*KEYS, "requests", "cost_usd", "long_context_requests"), 0)


def add(target, usage, model):
    for k in KEYS:
        target[k] += usage.get(k, 0)
    i, c, w, o = (usage.get(k, 0) for k in KEYS[:4])
    assert i >= c + w, "Overlapping cache accounting needs inspection"
    rates = RATES[model]
    long = i > 272000
    target["cost_usd"] += ((i-c-w)*rates[0] + c*rates[1] + w*rates[2]) * (2 if long else 1)/1e6 + o*rates[3]*(1.5 if long else 1)/1e6
    target["requests"] += 1
    target["long_context_requests"] += int(long)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions-root", type=Path, default=Path.home()/".codex/sessions")
    args = parser.parse_args()
    entries = re.findall(r"\| ([1-6])/player_([12]) \((Astra|Sol|Luna)\) \| (rollout-[^ |]+\.jsonl) \|", (ROOT/"README.md").read_text(encoding="utf-8"))
    assert len(entries) == 12
    totals = {m: {"full_session": empty(), "plan_requests": empty()} for m in RATES}
    sessions = []
    for setup, player, label, filename in entries:
        model = label.lower()
        matches = list(args.sessions_root.rglob(filename))
        assert len(matches) == 1, filename
        rows = [json.loads(line) for line in matches[0].read_text(encoding="utf-8").splitlines() if line.strip()]
        result = dict(setup=int(setup), participant=f"player_{player}", model="gpt-6-"+model, rollout=filename, full_session=empty(), plan_requests=empty(), max_request_input=0)
        seen = set()
        pending_plan = False
        contexts = set()
        efforts = set()
        tiers = set()
        last_total = None
        for row in rows:
            p = row.get("payload", {})
            if row["type"] == "turn_context":
                contexts.add(p.get("model"))
                efforts.add(p.get("effort"))
                tiers.add(p.get("service_tier"))
            if row["type"] == "response_item" and p.get("type") in ("custom_tool_call", "function_call"):
                name = p.get("name", "")
                body = p.get("input", p.get("arguments", ""))
                # Actual call expressions only: discovery strings are excluded.
                pending_plan |= "set_participant_plan" in name or bool(re.search(r"(?:tools\.)?mcp__doom_arena__set_participant_plan\s*\(", body))
            if row["type"] == "token_usage_record":
                rid = p["response_id"]
                if rid in seen:
                    continue
                seen.add(rid)
                u = p["usage"]
                add(result["full_session"], u, model)
                add(totals[model]["full_session"], u, model)
                if pending_plan:
                    add(result["plan_requests"], u, model)
                    add(totals[model]["plan_requests"], u, model)
                pending_plan = False
                result["max_request_input"] = max(result["max_request_input"], u["input_tokens"])
            if row["type"] == "event_msg" and p.get("type") == "token_count" and p.get("info"):
                last_total = p["info"]["total_token_usage"]
        assert contexts == {"gpt-6-"+model}, contexts
        assert seen, filename
        result["reconciles_to_final_token_count"] = all(result["full_session"][k] == last_total.get(k,0) for k in KEYS)
        assert result["reconciles_to_final_token_count"], filename
        result["reasoning_efforts"] = sorted(str(x) for x in efforts)
        result["recorded_service_tiers"] = sorted(str(x) for x in tiers)
        sessions.append(result)
    report = {"pricing_basis": "Standard API-equivalent USD; checked 2026-09-22; not a Codex invoice", "rates_per_million_input_cached_cachewrite_output": RATES, "models": totals, "sessions": sessions}
    (ROOT/"cost_analysis.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(totals, indent=2))
    print(json.dumps([{k:s[k] for k in ("setup","participant","model","max_request_input","reasoning_efforts","recorded_service_tiers")} for s in sessions]))


if __name__ == "__main__":
    main()
