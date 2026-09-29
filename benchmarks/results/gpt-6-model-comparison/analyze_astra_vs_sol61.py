"""Generate a standalone head-to-head report from series 7 and 8 only."""
import json
import statistics
from collections import Counter
from analyze_expanded import ROOT, LABELS, IDS, plan_outcome, ROUTE_ERRORS


def main():
    expanded = json.loads((ROOT/'expanded_analysis.json').read_text())
    models = {m: dict(matches=0, wins=0, hits=0, shots=0, damage=0, damage_taken=0,
                     latencies=[], outcomes=Counter(), full_cost=0, plan_cost=0)
              for m in ('sol61', 'astra')}
    seen = set()
    for series in expanded['series']:
        if series['setup'] not in (7, 8):
            continue
        pair = series['players']
        for p in sorted((ROOT/series['folder']).glob('*/summary.json')):
            s = json.loads(p.read_text())
            assert s['run_id'] not in seen
            seen.add(s['run_id'])
            assert s['terminal_reason'] in ('player_1_dead', 'player_2_dead')
            for i,m in enumerate(pair, 1):
                a=models[m]; pid=f'player_{i}'
                a['matches']+=1; a['wins']+=s['winner']==pid
                a['hits']+=s[f'{pid}_shots_hit']; a['shots']+=s[f'{pid}_shots_fired']
                a['damage']+=s[f'{pid}_damage_dealt']; a['damage_taken']+=s[f'player_{3-i}_damage_dealt']
            stats=json.loads((p.parent/'stats.json').read_text())
            calls={c['call_id']:c for c in stats['calls']}
            for c in calls.values():
                if c.get('tool_name')=='set_participant_plan' and c.get('participant_id') in ('player_1','player_2'):
                    models[pair[int(c['participant_id'][-1])-1]]['outcomes'][plan_outcome(c)]+=1
            for d in stats['inferred_decision_turns']:
                if d.get('participant_id') in ('player_1','player_2') and calls.get(d['intent_call_id'],{}).get('tool_name')=='set_participant_plan':
                    models[pair[int(d['participant_id'][-1])-1]]['latencies'].append(d['inferred_decision_latency_ms']/1000)
    for s in expanded['cost_sessions']:
        if s['setup'] in (7,8):
            m=next(m for m in models if IDS[m]==s['model'])
            models[m]['full_cost']+=s['full_session']['cost_usd']
            models[m]['plan_cost']+=s['plan_requests']['cost_usd']
    assert len(seen)==20 and models['sol61']['wins']==15 and models['astra']['wins']==5
    for a in models.values():
        l=a.pop('latencies'); a['decision_count']=len(l)
        a['mean_decision_seconds']=statistics.mean(l); a['median_decision_seconds']=statistics.median(l)
        a['invalid_routes']=sum(a['outcomes'][k] for k in ROUTE_ERRORS)
        a['validated_routes']=a['outcomes']['accepted']+a['invalid_routes']
    (ROOT/'astra-vs-sol61.json').write_text(json.dumps(dict(matches=20,models=models),indent=2)+'\n',encoding='utf-8')
    sol,astra=models['sol61'],models['astra']
    lines=['# GPT-6.1 Sol vs GPT-6 Astra in Doom', '',
    '**GPT-6.1 Sol won 15–5 (75%)** across 20 direct matches against GPT-6 Astra. Both models used medium reasoning and played ten matches from each player position.', '',
    '![GPT-6.1 Sol vs GPT-6 Astra: head-to-head win rate and output-token price](../../figures/astra-vs-sol61-token-price-vs-win-rate.png)', '',
    'This figure uses **only their direct matchup**, not their results against Sol or Luna. Its x-axis shows Standard output-token price, not total match cost. No draws occurred.', '',
    '## Results', '', '| Metric | GPT-6.1 Sol | GPT-6 Astra |', '|---|---:|---:|',
    '| Wins–losses | **15–5** | 5–15 |', '| Win rate | **75%** | 25% |']
    for label,key,fmt in [('Estimated full-session cost','full_cost','$.4f'),('Estimated plan-request cost','plan_cost','$.4f'),('Mean observation-to-plan time','mean_decision_seconds','.2f'),('Median observation-to-plan time','median_decision_seconds','.2f')]:
        values=[('$'+format(a[key],'.4f')) if fmt.startswith('$') else format(a[key],fmt)+' s' for a in (sol,astra)]
        lines.append(f'| {label} | {values[0]} | {values[1]} |')
    lines += [f"| Estimated cost per match | ${sol['full_cost']/20:.3f} | ${astra['full_cost']/20:.3f} |",
    f"| Shot accuracy (hits/shots) | {sol['hits']/sol['shots']:.1%} ({sol['hits']}/{sol['shots']}) | {astra['hits']/astra['shots']:.1%} ({astra['hits']}/{astra['shots']}) |",
    f"| Damage differential per match | {(sol['damage']-sol['damage_taken'])/20:+.2f} | {(astra['damage']-astra['damage_taken'])/20:+.2f} |", '',
    '## Main findings', '',
    '- **The win advantage held in both orientations:** 6.1 Sol won 8–2 as Player 1 and 7–3 as Player 2.',
    f"- **Lower estimated total usage cost:** ${sol['full_cost']:.2f} for 6.1 Sol versus ${astra['full_cost']:.2f} for Astra—{astra['full_cost']/sol['full_cost']:.2f}× less expensive under the Standard-rate estimate.",
    '- **Route validity and winning are different:** 6.1 Sol won more despite a higher route-rejection rate in this head-to-head subset. Do not substitute the expanded leaderboard’s pooled error rates here.', '',
    '## Route errors, separated from operational failures', '',
    '| Category | GPT-6.1 Sol | GPT-6 Astra |', '|---|---:|---:|']
    for label,k in [('Diagonal segment','diagonal'),('Blocked cell/crossing','blocked'),('Too many waypoints','waypoint_limit'),('Invalid stationary route','stationary'),('Post-finish submission (excluded)','post_finish'),('Controller/run mismatch (excluded)','run_mismatch')]:
        lines.append(f"| {label} | {sol['outcomes'][k]} | {astra['outcomes'][k]} |")
    lines += [f"| **Invalid / validated routes** | **{sol['invalid_routes']}/{sol['validated_routes']} ({sol['invalid_routes']/sol['validated_routes']:.1%})** | **{astra['invalid_routes']}/{astra['validated_routes']} ({astra['invalid_routes']/astra['validated_routes']:.1%})** |", '',
    'Route rejection counts the first four categories divided by accepted plus invalid route submissions. Retries are separate attempts. Post-finish and controller/run errors are excluded from numerator and denominator.', '',
    '## The two series', '', '| Player 1 | Player 2 | P1–P2 | Archive |', '|---|---|---:|---|',
    '| GPT-6.1 Sol | GPT-6 Astra | 8–2 | [Series 7](7_gpt-6.1-sol_vs_gpt-6-astra/) |',
    '| GPT-6 Astra | GPT-6.1 Sol | 3–7 | [Series 8](8_gpt-6-astra_vs_gpt-6.1-sol/) |', '',
    '## Measurement notes', '',
    '- Twenty unique matches recorded September 29, 2026; all ended in elimination. The original artifacts remain unchanged.',
    '- Model identities and medium reasoning come from verified Codex rollout turn contexts. Incorrect Astra readiness labels are corrected in the archive notes.',
    '- Costs are **API-equivalent estimates, not invoices or Codex subscription charges**. They include all requests in the four dedicated participant rollouts. Plan-request cost is a narrower subset. Service tier was not recorded; Standard rates are assumed.',
    '- Per-million token rates (input / cached / cache-write / output): 6.1 Sol $2 / $0.10 / $2.50 / $10; Astra $10 / $1 / $12.50 / $50. See [6.1 Sol pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and [Astra pricing](https://developers.openai.com/api/docs/models/gpt-6-astra); pricing basis is the same as the [combined report](README.md).',
    f"- Decision times pool {sol['decision_count']} recorded observation-to-plan intervals for 6.1 Sol and {astra['decision_count']} for Astra, including rejected attempts and orchestration. They are not pure model inference or time to an accepted plan.",
    '- The continuing-session design allows prior-round context. These are not 20 fully independent trials, and the scores alone do not establish adaptation, baiting, or a general model advantage.', '',
    '## Files and reproduction', '',
    '- [PNG figure](../../figures/astra-vs-sol61-token-price-vs-win-rate.png) · [SVG figure](../../figures/astra-vs-sol61-token-price-vs-win-rate.svg)',
    '- [Head-to-head metrics](astra-vs-sol61.json) · [Full 120-match report](README.md)',
    '- Run `python benchmarks/results/gpt-6-model-comparison/analyze_astra_vs_sol61.py`.',
    '- Run `python benchmarks/figures/generate_gpt61_token_price_chart.py --astra-vs-sol`.', '']
    (ROOT/'README-astra-vs-sol61.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(models,indent=2))


if __name__=='__main__': main()
