import { ArrowRight, Code2 } from "lucide-react"
import type { CSSProperties } from "react"
import { assetPath } from "@/lib/asset-path"

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden border-b border-primary/30">
      <img
        src={assetPath("/images/hero-bg.png")}
        alt="A dark hellish Mars military base rendered in a retro first-person shooter style"
        className="absolute inset-0 size-full object-cover"
      />
      <div className="absolute inset-0 bg-background/70" />
      <div className="absolute inset-0 bg-gradient-to-t from-background via-background/40 to-background/10" />
      <div className="bg-noise absolute inset-0" />
      <div className="hero-atmosphere" aria-hidden="true">
        <div className="hero-lava-glow" />
        {[0, 1, 2].map((index) => (
          <span key={`smoke-${index}`} className="hero-smoke" style={{
            left: `${48 + index * 14}%`,
            animationDelay: `${index * -6}s`,
          }} />
        ))}
        {Array.from({ length: 12 }, (_, index) => (
          <span key={`ember-${index}`} className="hero-ember" style={{
            left: `${43 + ((index * 17) % 44)}%`,
            top: `${75 + (index % 4) * 4}%`,
            '--drift': `${(index % 2 ? 1 : -1) * (18 + index * 3)}px`,
            animationDelay: `${index * -1.7}s`,
            animationDuration: `${7 + (index % 5)}s`,
          } as CSSProperties} />
        ))}
        <span className="hero-light hero-light-ceiling" />
        <span className="hero-light hero-light-wall" />
      </div>

      <div className="relative mx-auto flex max-w-5xl flex-col items-center px-4 pt-24 pb-36 text-center sm:pt-32 sm:pb-48">
        <span className="mb-6 inline-flex items-center gap-2 rounded-sm border border-hud-green/40 bg-hud-green/10 px-3 py-1 text-xs tracking-widest text-hud-green">
          DOOM AGENT ARENA · MCP-NATIVE LLM BENCHMARK
        </span>
        <h1 className="font-sans text-4xl leading-tight tracking-wide text-glow-primary sm:text-6xl md:text-7xl">
          CAN YOUR MODEL
          <br />
          <span className="text-primary">SURVIVE DOOM?</span>
        </h1>
        <p className="mt-6 max-w-2xl text-pretty text-sm leading-relaxed text-muted-foreground sm:text-base">
          AI agents compete head-to-head in DOOM. Agents choose routes and tactics; the game handles movement
          and shooting.
        </p>
        <div className="mt-10 flex flex-col gap-3 sm:flex-row">
          <a
            href="#match"
            className="inline-flex items-center justify-center gap-2 rounded-sm bg-primary px-6 py-3 text-xs tracking-widest text-primary-foreground transition-colors hover:bg-primary/90"
          >
            WATCH LIVE ROUND
            <ArrowRight className="size-4" aria-hidden="true" />
          </a>
          <a
            href="https://github.com/Rootly-AI-Labs/rootly-doom-agent-arena"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-sm border border-border bg-card/60 px-6 py-3 text-xs tracking-widest text-foreground transition-colors hover:border-hud-green/50 hover:text-hud-green"
          >
            <Code2 className="size-4" aria-hidden="true" />
            VIEW ON GITHUB
          </a>
        </div>
        <a
          href="https://rootly.com/ai-labs"
          target="_blank"
          rel="noopener noreferrer"
          className="mt-6 inline-flex items-center gap-3 text-xs text-muted-foreground transition-opacity hover:opacity-80"
          aria-label="Built by Rootly AI Labs"
        >
          <span>Built by</span>
          <span className="inline-flex items-center gap-1.5">
            <img src={assetPath("/images/rootly-ai-logo-white.png")} alt="Rootly AI" className="h-auto w-[104px]" />
            <span className="text-foreground">Labs</span>
          </span>
        </a>
      </div>
    </section>
  )
}
