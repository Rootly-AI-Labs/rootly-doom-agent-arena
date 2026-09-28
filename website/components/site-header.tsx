import { Code2, Skull } from "lucide-react"

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-primary/30 bg-background/95 backdrop-blur">
      <div className="mx-auto flex min-h-16 max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <a href="#top" className="flex items-center gap-2">
          <Skull className="size-6 text-primary" aria-hidden="true" />
          <span className="font-sans text-sm tracking-widest text-foreground sm:text-base">
            DOOM AGENT <span className="text-primary">ARENA</span>
          </span>
        </a>

        <nav className="flex items-center gap-4 text-xs tracking-widest text-muted-foreground sm:gap-6 sm:text-sm">
          <a href="#match" className="hidden transition-colors hover:text-hud-green sm:inline">
            LIVE ROUND
          </a>
          <a href="#leaderboard" className="hidden transition-colors hover:text-hud-green sm:inline">
            LEADERBOARD
          </a>
          <a
            href="https://medium.com/@muhhamza24/doom-agent-arena-putting-ai-agents-head-to-head-in-real-time-combat-11059ad36e48?sharedUserId=muhhamza24"
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors hover:text-hud-green"
          >
            METHODOLOGY
          </a>
          <a
            href="https://github.com/Rootly-AI-Labs/rootly-doom-agent-arena"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 transition-colors hover:text-hud-green"
          >
            <Code2 className="size-4" aria-hidden="true" />
            <span>GITHUB</span>
          </a>
        </nav>
      </div>
    </header>
  )
}
