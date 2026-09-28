import { Trophy, Zap, Target, Flame, DollarSign } from "lucide-react"
import { leaderboard, legacyLeaderboard, type LeaderboardEntry } from "@/lib/benchmark-data"

const badgeConfig = {
  winrate: { icon: Trophy, label: "Win rate leader" },
  speed: { icon: Zap, label: "Fastest decisions" },
  accuracy: { icon: Target, label: "Most accurate" },
  damage: { icon: Flame, label: "Best damage differential" },
  cost: { icon: DollarSign, label: "Best win rate per cost" },
} as const

export function Leaderboard() {
  return (
    <section id="leaderboard" className="bg-background">
      <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-24">
        <div className="mb-10 flex flex-col items-center gap-2 text-center">
          <h2 className="font-sans text-3xl tracking-wide sm:text-4xl">LEADERBOARD</h2>
          <span className="text-xs tracking-widest text-primary">60 MATCHES · 40 PER MODEL · MEDIUM REASONING</span>
          <p className="max-w-xl text-sm text-muted-foreground">
            Each pair played 20 matches, swapping sides after 10. All matches ended in elimination, with no draws.
          </p>
        </div>

        <LeaderboardTable entries={leaderboard} />
        <details className="group mt-3 rounded-sm border border-border bg-card">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-4 text-xs tracking-widest text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
            VIEW LEGACY RESULTS
            <span aria-hidden="true" className="text-lg text-primary group-open:rotate-45">+</span>
          </summary>
          <div className="border-t border-border p-3">
            <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
              Original four-model tournament · 60 rounds per model · draw-adjusted win rates.
              Different opponents and cost methodology; not directly comparable with the current leaderboard.
            </p>
            <LeaderboardTable entries={legacyLeaderboard} />
          </div>
        </details>

        <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">
          Badges mark the category leader: <Trophy className="inline size-3 text-primary" aria-hidden="true" /> win
          rate · <Zap className="inline size-3 text-primary" aria-hidden="true" /> fastest decisions ·{" "}
          <Target className="inline size-3 text-primary" aria-hidden="true" /> accuracy ·{" "}
          <Flame className="inline size-3 text-primary" aria-hidden="true" /> damage differential ·{" "}
          <DollarSign className="inline size-3 text-primary" aria-hidden="true" /> cost efficiency. Data reflects the
          latest Doom Agent Arena README results for GPT-6 Astra, Sol, and Luna.
        </p>
        <p className="mt-3 text-center text-xs leading-relaxed text-muted-foreground">
          <a className="underline hover:text-foreground" href="https://github.com/Rootly-AI-Labs/rootly-doom-agent-arena/blob/main/benchmarks/results/gpt-6-model-comparison/README.md" target="_blank" rel="noreferrer">
            Results and methodology
          </a>
        </p>
      </div>
    </section>
  )
}

function LeaderboardTable({ entries }: { entries: LeaderboardEntry[] }) {
  return (
        <div className="overflow-x-auto rounded-sm border border-border bg-card">
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border text-[10px] tracking-[0.2em] text-muted-foreground">
                <th className="px-4 py-3">RANK</th>
                <th className="px-4 py-3">MODEL</th>
                <th className="px-4 py-3 text-right">W-L</th>
                <th className="px-4 py-3">WIN RATE</th>
                <th className="px-4 py-3 text-right">DECISION SPEED</th>
                <th className="px-4 py-3 text-right">ACCURACY</th>
                <th className="px-4 py-3 text-right">DAMAGE DIFF</th>
                <th className="px-4 py-3 text-right">WIN RATE / COST</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const isTopThree = entry.rank <= 3

                return (
                  <tr
                    key={entry.model}
                    className="border-b border-border last:border-b-0 transition-colors hover:bg-primary/5"
                  >
                    <td className="px-4 py-4 font-sans text-base tracking-wide">
                      {isTopThree ? (
                        <span className="flex items-center gap-1.5 text-hud-green">
                          <Trophy className="size-3.5" aria-hidden="true" />
                          {entry.rank}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">{entry.rank}</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2">
                        <p className="font-mono text-sm text-foreground sm:text-base">{entry.model}</p>
                        {entry.badges.map((badge) => {
                          const { icon: Icon, label } = badgeConfig[badge]
                          return (
                            <span key={badge} title={label} className="text-primary">
                              <Icon className="size-3.5" aria-hidden="true" />
                              <span className="sr-only">{label}</span>
                            </span>
                          )
                        })}
                      </div>
                    </td>
                    <td className="px-4 py-4 text-right font-mono text-xs text-foreground sm:text-sm">
                      {entry.wins}-{entry.losses}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-sm bg-muted">
                          <div className="h-full bg-hud-green" style={{ width: `${entry.winRate}%` }} />
                        </div>
                        <span className="text-xs text-muted-foreground">{entry.winRate.toFixed(1)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-right font-mono text-xs text-foreground sm:text-sm">
                      {entry.decisionSpeed}
                    </td>
                    <td className="px-4 py-4 text-right font-mono text-xs text-foreground sm:text-sm">
                      {entry.accuracy}%
                    </td>
                    <td className="px-4 py-4 text-right font-mono text-xs sm:text-sm">
                      <span className={entry.damageDiff >= 0 ? "text-hud-green" : "text-destructive"}>
                        {entry.damageDiff >= 0 ? "+" : ""}
                        {entry.damageDiff.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-right font-mono text-xs text-primary sm:text-sm">
                      {entry.costEfficiency}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
  )
}
