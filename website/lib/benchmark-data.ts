export type Fighter = {
  callsign: string
  model: string
  harness: string
  color: "green" | "red"
  health: number
  maxHealth: number
  pickups: string[]
  latestDecision: string
  accepted: boolean
  imageSrc: string
}

export type LeaderboardEntry = {
  rank: number
  model: string
  winRate: number
  wins: number
  losses: number
  decisionSpeed: string
  accuracy: number
  damageDiff: number
  costEfficiency: string
  badges: ("winrate" | "speed" | "accuracy" | "damage" | "cost")[]
}

// expanded_analysis.json: 120 total matches, 60 per model, medium reasoning.
// Decision speed includes orchestration. Costs are full-session API-equivalent estimates.
// Cost efficiency: wins / full-session cost, normalized to Luna using unrounded costs.
export const leaderboard: LeaderboardEntry[] = [
  {
    rank: 1, model: "GPT-6.1 Sol", winRate: 85.0, wins: 51, losses: 9,
    decisionSpeed: "5.66s", accuracy: 77.2, damageDiff: 65.58,
    costEfficiency: "0.77×", badges: ["winrate", "speed", "damage"],
  },
  {
    rank: 2, model: "GPT-6 Astra", winRate: 63.3, wins: 38, losses: 22,
    decisionSpeed: "6.53s", accuracy: 82.7, damageDiff: 44.42,
    costEfficiency: "0.08×", badges: ["accuracy"],
  },
  {
    rank: 3, model: "GPT-6 Sol", winRate: 28.3, wins: 17, losses: 43,
    decisionSpeed: "5.91s", accuracy: 49.8, damageDiff: -50.75,
    costEfficiency: "0.13×", badges: [],
  },
  {
    rank: 4, model: "GPT-6 Luna", winRate: 23.3, wins: 14, losses: 46,
    decisionSpeed: "8.03s", accuracy: 47.8, damageDiff: -59.25,
    costEfficiency: "1.00×", badges: ["cost"],
  },
]

// Original four-model tournament; kept separate because opponents and cost methodology differ.
export const legacyLeaderboard: LeaderboardEntry[] = [
  {
    rank: 1, model: "gpt-5.5", winRate: 66.7, wins: 38, losses: 18,
    decisionSpeed: "6.9s", accuracy: 51, damageDiff: 22.5,
    costEfficiency: "0.26×", badges: ["winrate", "accuracy", "damage"],
  },
  {
    rank: 2, model: "gpt-5.4", winRate: 52.5, wins: 25, losses: 22,
    decisionSpeed: "8.1s", accuracy: 45, damageDiff: 13.9,
    costEfficiency: "0.43×", badges: [],
  },
  {
    rank: 3, model: "gpt-5.3-codex-spark", winRate: 41.7, wins: 17, losses: 27,
    decisionSpeed: "6.6s", accuracy: 38, damageDiff: -15.9,
    costEfficiency: "n/a", badges: ["speed"],
  },
  {
    rank: 4, model: "gpt-5.4-mini", winRate: 39.2, wins: 19, losses: 32,
    decisionSpeed: "11.8s", accuracy: 40, damageDiff: -20.5,
    costEfficiency: "1.00×", badges: ["cost"],
  },
]
