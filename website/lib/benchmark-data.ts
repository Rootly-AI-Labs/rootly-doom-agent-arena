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

// Latest README tournament: 60 total matches, 40 per model, medium reasoning.
// Decision speed includes orchestration. Costs are full-session API-equivalent estimates.
export const leaderboard: LeaderboardEntry[] = [
  {
    rank: 1, model: "GPT-6 Astra", winRate: 82.5, wins: 33, losses: 7,
    decisionSpeed: "6.33s", accuracy: 83.2, damageDiff: 86.25,
    costEfficiency: "0.10×", badges: ["winrate", "accuracy", "damage"],
  },
  {
    rank: 2, model: "GPT-6 Sol", winRate: 42.5, wins: 17, losses: 23,
    decisionSpeed: "5.34s", accuracy: 57.6, damageDiff: -24.50,
    costEfficiency: "0.18×", badges: ["speed"],
  },
  {
    rank: 3, model: "GPT-6 Luna", winRate: 25.0, wins: 10, losses: 30,
    decisionSpeed: "7.57s", accuracy: 52.4, damageDiff: -61.75,
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
