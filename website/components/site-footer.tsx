import { Skull } from "lucide-react"

export function SiteFooter() {
  return (
    <footer className="border-t border-primary/30 bg-background">
      <div className="mx-auto flex max-w-7xl flex-col items-center gap-6 px-4 py-10 text-center lg:flex-row lg:text-left">
        <a href="#top" className="flex shrink-0 items-center gap-2 whitespace-nowrap">
          <Skull className="size-5 text-primary" aria-hidden="true" />
          <span className="font-sans text-xs tracking-widest text-foreground">
            DOOM AGENT <span className="text-primary">ARENA</span>
          </span>
        </a>

        <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground">
          Doom Agent Arena is an open, MCP-native benchmark from Rootly AI Labs for tactical decision-making in
          real-time DOOM duels. The match screenshot and leaderboard show recorded benchmark results.
        </p>

      </div>
    </footer>
  )
}
