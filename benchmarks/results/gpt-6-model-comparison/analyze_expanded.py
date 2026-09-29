"""Reproduce the 120-match analysis; exports aggregates, never raw credentials.

Original 12 rollout costs are preserved in cost_analysis.json. Supplemental
rollouts are checked against model metadata and cumulative token counts.
"""
import json
from pathlib import Path
from collections import Counter, defaultdict
import statistics
import re
import calculate_costs as billing

ROOT = Path(__file__).resolve().parent
MODELS = ['sol61', 'astra', 'sol', 'luna']
LABELS = dict(sol61='GPT-6.1 Sol', astra='GPT-6 Astra', sol='GPT-6 Sol', luna='GPT-6 Luna')
IDS = dict(sol61='gpt-6.1-sol', astra='gpt-6-astra', sol='gpt-6-sol', luna='gpt-6-luna')
billing.RATES['sol61'] = (2, .1, 2.5, 10)
PAIRS = [('astra','sol'), ('sol','astra'), ('astra','luna'), ('luna','astra'), ('sol','luna'), ('luna','sol'), ('sol61','astra'), ('astra','sol61'), ('sol61','sol'), ('sol','sol61'), ('sol61','luna'), ('luna','sol61')]
ROLLOUTS = [
('rollout-2026-09-29T13-33-22-01a0ee3a-6c73-7060-b768-8f0194337202.jsonl', 'rollout-2026-09-29T13-33-30-01a0ee3a-8b82-74c0-b0fe-cdf982e15d81.jsonl'),
('rollout-2026-09-29T13-58-23-01a0ee51-55af-7420-a0f8-8c6e358eccc6.jsonl', 'rollout-2026-09-29T13-58-27-01a0ee51-6588-7d20-8b86-2351f031ce09.jsonl'),
('rollout-2026-09-29T14-12-03-01a0ee5d-d60f-7770-af21-3d63933952d1.jsonl', 'rollout-2026-09-29T14-14-09-01a0ee5f-c1fb-7222-ae22-2e3fee95e80e.jsonl'),
('rollout-2026-09-29T14-47-34-01a0ee7e-5b81-76b2-8542-a4f1e03fd591.jsonl', 'rollout-2026-09-29T14-47-29-01a0ee7e-4807-7a12-9097-bc5389729fda.jsonl'),
('rollout-2026-09-29T15-00-25-01a0ee8a-20c7-7d32-9bb1-c80216bc0754.jsonl', 'rollout-2026-09-29T15-00-28-01a0ee8a-2ba2-7382-923a-ac9360323075.jsonl'),
('rollout-2026-09-29T15-49-33-01a0eeb7-1a35-7b62-a03d-aa34bb2eabea.jsonl', 'rollout-2026-09-29T15-49-37-01a0eeb7-28f8-7080-a455-c3ed37395de6.jsonl'),
]

def plan_outcome(call):
    """Classify explicit validation results separately from operational failures."""
    error = str(call.get('error', '')).lower()
    if call.get('accepted') is True and not call.get('is_error'):
        return 'accepted'
    if 'already finished' in error:
        return 'post_finish'
    if 'controller token file' in error and 'run_id' in error:
        return 'run_mismatch'
    if call.get('accepted') is False:
        if 'diagonal' in error:
            return 'diagonal'
        if 'blocked cell' in error or 'blocked wall cell' in error:
            return 'blocked'
        if 'at most 8 waypoints' in error:
            return 'waypoint_limit'
        if 'does not move' in error:
            return 'stationary'
    raise AssertionError(f'Unclassified plan outcome: {call.get("call_id")}')


ROUTE_ERRORS = ('diagonal', 'blocked', 'waypoint_limit', 'stationary')


def main():
    old = json.loads((ROOT/'cost_analysis.json').read_text())
    costs = old['sessions'].copy()
    for setup, filenames in enumerate(ROLLOUTS, 7):
        for player, filename in enumerate(filenames, 1):
            model = PAIRS[setup-1][player-1]
            path = Path.home()/'.codex/sessions/2026/09/29'/filename
            result = dict(setup=setup, participant=f'player_{player}', model=IDS[model], rollout=filename, full_session=billing.empty(), plan_requests=billing.empty())
            seen, contexts, efforts, tiers = set(), set(), set(), set()
            pending, last_total = False, None
            for line in path.read_text(encoding='utf-8').splitlines():
                row=json.loads(line); p=row.get('payload', {})
                if row['type']=='turn_context':
                    contexts.add(p.get('model')); efforts.add(p.get('effort')); tiers.add(str(p.get('service_tier')))
                if row['type']=='response_item' and p.get('type') in ('custom_tool_call','function_call'):
                    body=p.get('input',p.get('arguments',''))
                    pending |= 'set_participant_plan' in p.get('name','') or bool(re.search(r'(?:tools\.)?\w*set_participant_plan\s*\(',body))
                if row['type']=='token_usage_record' and p['response_id'] not in seen:
                    seen.add(p['response_id']); u=p['usage']
                    billing.add(result['full_session'],u,model)
                    if pending: billing.add(result['plan_requests'],u,model)
                    pending=False
                if row['type']=='event_msg' and p.get('type')=='token_count' and p.get('info'):
                    last_total=p['info']['total_token_usage']
            assert contexts=={IDS[model]}, (filename,contexts)
            assert efforts=={'medium'}, (filename,efforts)
            assert seen and last_total
            assert all(result['full_session'][k]==last_total.get(k,0) for k in billing.KEYS), filename
            result.update(reconciles_to_final_token_count=True, reasoning_efforts=sorted(efforts), recorded_service_tiers=sorted(tiers))
            costs.append(result)
    totals={m:dict(matches=0,wins=0,damage=0,damage_taken=0,hits=0,shots=0,p1_wins=0,p2_wins=0,plan_calls=0,rejected_plans=0,latencies=[],full_session=billing.empty(),plan_requests=billing.empty()) for m in MODELS}
    for c in costs:
        m=next(m for m in MODELS if IDS[m]==c['model'])
        for kind in ('full_session','plan_requests'):
            for k,v in c[kind].items(): totals[m][kind][k]+=v
    series=[]; run_ids=set(); head=defaultdict(Counter)
    error_counts = {m: Counter() for m in MODELS}
    error_cohorts = {'original': {m: Counter() for m in MODELS}, 'extension': {m: Counter() for m in MODELS}}
    for setup,pair in enumerate(PAIRS,1):
        folders=list(ROOT.glob(f'{setup}_*')); assert len(folders)==1
        paths=sorted(folders[0].glob('*/summary.json')); assert len(paths)==10
        score=Counter(); rounds=[]
        for path in paths:
            s=json.loads(path.read_text()); assert s['run_id'] not in run_ids
            run_ids.add(s['run_id']); rounds.append(s['round'])
            assert s['winner'] in ('player_1','player_2'), s
            score[s['winner']]+=1
            for i,m in enumerate(pair,1):
                t=totals[m]; pid=f'player_{i}'; opp=f'player_{3-i}'
                t['matches']+=1; won=s['winner']==pid; t['wins']+=won
                t[f'p{i}_wins']+=won
                head[m][pair[2-i]]+=won
                t['damage']+=s[f'{pid}_damage_dealt']; t['damage_taken']+=s[f'{opp}_damage_dealt']
                t['hits']+=s[f'{pid}_shots_hit']; t['shots']+=s[f'{pid}_shots_fired']
            stats=json.loads((path.parent/'stats.json').read_text())
            calls={c['call_id']:c for c in stats['calls']}
            for c in calls.values():
                if c.get('tool_name')=='set_participant_plan' and c.get('participant_id') in ('player_1','player_2'):
                    t=totals[pair[int(c['participant_id'][-1])-1]]
                    t['plan_calls']+=1
                    t['rejected_plans']+=bool(c.get('is_error') or c.get('accepted') is False)
                    model = pair[int(c['participant_id'][-1])-1]
                    outcome = plan_outcome(c)
                    error_counts[model][outcome] += 1
                    error_cohorts['original' if setup <= 6 else 'extension'][model][outcome] += 1
            for d in stats['inferred_decision_turns']:
                pid=d.get('participant_id'); value=d.get('inferred_decision_latency_ms')
                if pid in ('player_1','player_2') and value is not None and calls.get(d['intent_call_id'],{}).get('tool_name')=='set_participant_plan':
                    totals[pair[int(pid[-1])-1]]['latencies'].append(value)
        assert sorted(rounds)==list(range(1,11))
        series.append(dict(setup=setup,folder=folders[0].name,players=pair,p1_wins=score['player_1'],p2_wins=score['player_2']))
    assert len(run_ids)==120 and all(t['matches']==60 for t in totals.values())
    for t in totals.values():
        l=t.pop('latencies'); t['decision_count']=len(l)
        t['mean_decision_seconds']=statistics.mean(l)/1000
        t['median_decision_seconds']=statistics.median(l)/1000
    for m, counts in error_counts.items():
        invalid = sum(counts[k] for k in ROUTE_ERRORS)
        validated = counts['accepted'] + invalid
        assert sum(counts.values()) == totals[m]['plan_calls']
        assert invalid + counts['post_finish'] + counts['run_mismatch'] == totals[m]['rejected_plans']
        totals[m]['plan_outcomes'] = dict(counts)
        totals[m]['route_validation_attempts'] = validated
        totals[m]['route_rejections'] = invalid
        totals[m]['route_rejection_rate'] = invalid / validated
    report=dict(matches=120,models=totals,head_to_head=head,series=series,cost_sessions=costs,rates=billing.RATES,pricing_basis='Standard API-equivalent estimate, not actual billing; 6.1 rates checked 2026-09-29')
    report['plan_outcome_cohorts'] = error_cohorts
    (ROOT/'expanded_analysis.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    write_report(report)
    print(json.dumps(totals,indent=2))

def write_report(r):
    t=r['models']; sol=t['sol61']; cost=sol['full_session']['cost_usd']
    lines=['# GPT-6.1 Sol in Doom: 51 wins in 60 matches', '',
    'GPT-6.1 Sol won **51–9 (85%)** against GPT-6 Astra, Sol, and Luna: 20 matches per opponent, with player positions swapped after each ten-match series. The full four-model archive now contains **120 unique completed matches**, with **60 appearances per model**.', '',
    '![GPT-6.1 Sol and GPT-6 models: win rate versus output-token price](../../figures/gpt-6.1-output-token-price-vs-win-rate.png)', '',
    'The figure uses all 120 matches, not the earlier three-model percentages. Its x-axis is Standard output-token price, **not total match cost**. All matches have a winner, so draw-adjusted score equals win rate.', '',
    '## Most interesting results', '',
    '- **6.1 Sol won every matchup:** 15–5 against Astra, 20–0 against Sol, and 16–4 against Luna. It won all six ten-match series, including both player orientations.',
    '- **The clearest upgrade is against the older Sol:** 20 wins from 20 head-to-head rounds. Both have a $10/M output-token price; 6.1 has a lower cached-input rate ($0.10/M versus $0.20/M).',
    f'- **Strong results at modest estimated usage cost:** 6.1 Sol cost **${cost:.2f} total**, **${cost/60:.3f} per match**, or **${cost/51:.3f} per win**. These include logged observation, polling, setup, and retry requests—not only plan-generating requests.',
    '- **The advantage persisted on both sides:** 27/30 wins as Player 1 (90%) and 24/30 as Player 2 (80%). It was not confined to one spawn orientation.',
    f"- **Winning did not mean flawless route generation:** 6.1 Sol had {sol['route_rejections']}/{sol['route_validation_attempts']} invalid route submissions ({sol['route_rejection_rate']:.1%}), versus {t['astra']['route_rejections']}/{t['astra']['route_validation_attempts']} for Astra ({t['astra']['route_rejection_rate']:.1%}). Post-finish and controller/run errors are excluded from both numerator and denominator; retries remain included. See the full error breakdown below.",
    '- **Astra still had the higher shot hit rate:** 82.7% versus 77.2% for 6.1 Sol, yet 6.1 won more matches. Shot accuracy alone does not explain victory.',
    '- **Luna remains the cheapest:** approximately $1.20 across its 60 appearances, but won 14/60. Its estimated wins per dollar remain higher than 6.1 Sol’s; the strongest win rate and the cheapest wins are different objectives.', '',
    'These are descriptive results from this benchmark, not proof of general model superiority or a causal explanation of strategy.', '',
    '## GPT-6.1 Sol head-to-head', '',
    '| Opponent | 6.1 as P1 | 6.1 as P2 | Combined 6.1 wins–losses | Win rate |',
    '|---|---:|---:|---:|---:|',
    '| GPT-6 Astra | 8–2 | 7–3 | **15–5** | 75% |',
    '| GPT-6 Sol | 10–0 | 10–0 | **20–0** | 100% |',
    '| GPT-6 Luna | 9–1 | 7–3 | **16–4** | 80% |', '',
    '## Expanded leaderboard', '',
    '| Model | Wins–losses | Win rate | Mean decision time | Shot accuracy | Damage differential / match | Estimated full-session cost |',
    '|---|---:|---:|---:|---:|---:|---:|']
    for m in MODELS:
        a=t[m]
        lines.append(f"| {LABELS[m]} | {a['wins']}–{60-a['wins']} | {a['wins']/60:.1%} | {a['mean_decision_seconds']:.2f} s | {a['hits']/a['shots']:.1%} | {(a['damage']-a['damage_taken'])/60:+.2f} | ${a['full_session']['cost_usd']:.2f} |")
    lines += ['', 'Decision time is the pooled interval from observation completion to a plan submission, including orchestration and rejected attempts. It is **not model-server inference time**, and retry intervals may share an observation. Counts: 443 for 6.1 Sol, 351 Astra, 299 Sol, and 315 Luna. 6.1 Sol’s median is 5.31 s. Accuracy is pooled hits/shots, not an average of round percentages.', '']
    lines += ['## Route validation and operational errors', '',
    '**Route rejection rate = invalid route submissions / (accepted + invalid route submissions).** Count each attempted call, including retries. Operational failures did not reach route validation and are excluded from this rate. Unknown error messages cause the analysis to fail for manual review rather than being silently assigned to a category.', '',
    '| Error type | Meaning | Route-generation error? |', '|---|---|---|',
    '| Diagonal segment | Consecutive waypoints change both row and column | Yes |',
    '| Blocked cell/crossing | Route enters or crosses a wall | Yes |',
    '| Too many waypoints | Route exceeds the eight-waypoint limit | Yes |',
    '| Invalid stationary route | No movement without the required hold objective/policy | Yes |',
    '| Post-finish submission | Plan arrives after the match finishes | No |',
    '| Controller-token/run mismatch | Client and controller refer to different rounds | No |', '',
    '| Model | Diagonal | Blocked | Too many waypoints | Stationary | Invalid / validated | Route rejection rate |',
    '|---|---:|---:|---:|---:|---:|---:|']
    for m in MODELS:
        a=t[m]; c=a['plan_outcomes']
        lines.append(f"| {LABELS[m]} | {c.get('diagonal',0)} | {c.get('blocked',0)} | {c.get('waypoint_limit',0)} | {c.get('stationary',0)} | {a['route_rejections']}/{a['route_validation_attempts']} | {a['route_rejection_rate']:.1%} |")
    lines += ['', '| Model | Post-finish | Run mismatch | All plan calls | Combined errors / all calls (not route rejection) |', '|---|---:|---:|---:|---:|']
    for m in MODELS:
        a=t[m]; c=a['plan_outcomes']
        lines.append(f"| {LABELS[m]} | {c.get('post_finish',0)} | {c.get('run_mismatch',0)} | {a['plan_calls']} | {a['rejected_plans']}/{a['plan_calls']} ({a['rejected_plans']/a['plan_calls']:.1%}) |")
    lines += ['', '### Why this differs from the earlier Jev comparison', '',
    'The earlier [Jev–Astra report](../jev_astra/analysis.md) counted 27 explicit invalid routes out of 235 submissions (11.5%). The previously highlighted 31.2%/30.9% here combined invalid routes with operational failures; those are not equivalent metrics. The combined figures remain above for auditing, not as route-generation scores.', '',
    '| Cohort | Model | Invalid / validated | Route rejection rate |', '|---|---|---:|---:|']
    for cohort, groups in r['plan_outcome_cohorts'].items():
        for m in MODELS:
            c=groups[m]; invalid=sum(c[k] for k in ROUTE_ERRORS); validated=c['accepted']+invalid
            if validated:
                label='Original GPT-6 series 1–6' if cohort=='original' else '6.1 extension series 7–12'
                lines.append(f'| {label} | {LABELS[m]} | {invalid}/{validated} | {invalid/validated:.1%} |')
    lines += ['', 'Astra’s 6.1-extension rate is closer to the earlier Jev result; its original GPT-6 series raise the pooled rate. Different opponents, dates, trajectories, and continuing-session history mean this is not evidence of a model regression. Jev also receives generated, validated routes, so its route-error rate is not a like-for-like route-construction comparison.', '',
    '**Correction scope:** only error categorization and its denominator changed. Match outcomes, token costs, shot accuracy, damage, existing observation-to-submission timings, and the win-rate/token-price figure are unchanged. The timing metric is not time to a valid plan.', '',
    '## Cost and token accounting', '',
    'Costs are **Standard API-equivalent estimates, not actual invoices or Codex subscription charges**. Pricing source: [official GPT-6.1 Sol model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol), checked September 29, 2026; [official API pricing](https://developers.openai.com/api/docs/pricing) for the original models.', '',
    '| 6.1 Sol usage across six sessions | Amount |', '|---|---:|',
    f"| Full-session estimated cost | ${cost:.6f} |",
    f"| Plan-producing requests only | ${sol['plan_requests']['cost_usd']:.6f} |",
    f"| Other session requests | ${cost-sol['plan_requests']['cost_usd']:.6f} |",
    '| Total input tokens | 37,965,681 |', '| Cached input (included above) | 37,347,584 |', '| Uncached input | 618,097 |', '| Cache-write tokens | 0 |', '| Output tokens | 71,972 |', '| Reasoning output (included above) | 4,791 |', '| Model requests | 664 |', '| Plan-producing model requests | 269 |', '',
    '6.1 rates per million: **$2 uncached input, $0.10 cached input, $2.50 cache writes, $10 output**. Cached input is 98.37% of input usage. Reasoning is already included in output, not charged twice. The script deduplicates by response ID and reconciles each supplemental rollout to its final cumulative token count. No included request exceeds 272K input tokens. Service tier was not recorded, so Fast/regional surcharges are not assumed.', '',
    'Formula: `(uncached input × input rate + cached input × cache rate + cache writes × write rate + output × output rate) / 1,000,000`.', '',
    'Astra’s estimated full-session cost across its 60 matches was $40.30 versus $5.69 for 6.1 Sol (7.08×). Across just their 20 head-to-head matches, Astra cost $14.92 versus $1.69 for 6.1 Sol (8.85×). These compare logged usage under Standard rates, not billed charges.', '',
    '| Series | 6.1 Sol estimated cost |', '|---|---:|']
    for c in r['cost_sessions']:
        if c['model']==IDS['sol61']:
            row=r['series'][c['setup']-1]
            lines.append(f"| {LABELS[row['players'][0]]} vs {LABELS[row['players'][1]]} | ${c['full_session']['cost_usd']:.4f} |")
    lines += ['', 'Full-session costs include all recorded requests in the dedicated participant rollouts. Plan-request costs count a request once if it emits any plan submission, including retries/batched tools. This differs from arena plan-call and decision-interval counts.', '',
    '## Completed series', '', '| # | Archive | Player 1 | Player 2 | P1–P2 |', '|---|---|---|---|---:|']
    for s in r['series']:
        lines.append(f"| {s['setup']} | [{s['folder']}]({s['folder']}/) | {LABELS[s['players'][0]]} | {LABELS[s['players'][1]]} | {s['p1_wins']}–{s['p2_wins']} |")
    lines += ['', 'The final series is `session_f2da9a461021`: Clipboard Cowboy (GPT-6 Luna) vs Panic Ravioli (GPT-6.1 Sol), 3–7. Both identities and medium reasoning were verified from actual Codex turn contexts. It was moved into folder 12; all ten summary hashes were preserved. Earlier partial/restarted sessions, including `session_727df085b217`, are excluded. Archived copies of series 10 and 11 must not be counted again from their original directories.', '',
    '## Methodology and limitations', '',
    '- Six model pairs, two orientations per pair, ten matches per orientation. Each model faces every other model 20 times, with 30 appearances per player side.',
    '- All 120 run IDs are unique; each included series contains rounds 1–10. There are 119 eliminations and one health-at-timeout result (series 11, round 1, won by 6.1 Sol). No draws.',
    '- Original GPT-6 matchups were recorded September 22; the 6.1 extension was recorded September 29. This is a combined historical leaderboard, **not a simultaneously rerun, fully frozen-version experiment**. Prompt/controller/UI changes and session continuity may confound cross-date comparisons.',
    '- Within-series prior-round context can affect play. Ten rounds in a continuing session should not be treated as ten fully independent trials; no significance claim is made.',
    '- Model labels in several readiness records were wrong. Series 7/8 Astra and series 11 Luna use verified rollout identities documented in their archive notes; raw match artifacts were not rewritten.',
    '- This compares complete agent systems, including the route controller, tool overhead, retries, and allowed history. No strategic explanation such as baiting or adaptation is inferred from the score alone.', '',
    '## Reproduce and inspect', '',
    '- Run `python benchmarks/results/gpt-6-model-comparison/analyze_expanded.py` with the indexed local Codex rollouts available.',
    '- Run `python benchmarks/figures/generate_gpt61_token_price_chart.py` to regenerate the PNG and SVG.',
    '- [Expanded metrics and cost/session manifest](expanded_analysis.json)',
    '- [Original cost audit](cost_analysis.json) and [previous report preserved before this update](README-pre-6.1-update.md)',
    '- [Full-resolution PNG](../../figures/gpt-6.1-output-token-price-vs-win-rate.png) · [SVG](../../figures/gpt-6.1-output-token-price-vs-win-rate.svg)', '']
    (ROOT/'README.md').write_text('\n'.join(lines),encoding='utf-8')

if __name__=='__main__': main()
