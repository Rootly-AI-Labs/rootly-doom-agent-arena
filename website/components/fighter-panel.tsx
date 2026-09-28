import { CheckCircle2, Heart } from "lucide-react"
import type { Fighter } from "@/lib/benchmark-data"
import { cn } from "@/lib/utils"
import { assetPath } from "@/lib/asset-path"

export function FighterPanel({ fighter, align = "left" }: { fighter: Fighter; align?: "left" | "right" }) {
  const isGreen = fighter.color === "green"
  const accentText = isGreen ? "text-hud-green" : "text-primary"
  const accentBorder = isGreen ? "border-hud-green" : "border-primary"
  const accentGlow = isGreen ? "text-glow-hud" : "text-glow-primary"
  const healthPct = Math.round((fighter.health / fighter.maxHealth) * 100)

  return (
    <div className="flex flex-col gap-3">
      <div className={cn("flex flex-col gap-1", align === "right" && "sm:items-end sm:text-right")}>
        <span className="text-[10px] tracking-[0.2em] text-muted-foreground">MODEL CHOSEN NAME</span>
        <h3 className={cn("font-sans text-2xl tracking-wide sm:text-3xl", accentText, accentGlow)}>
          {fighter.callsign}
        </h3>
        <p className="text-xs text-muted-foreground sm:text-sm">
          model: <span className="text-foreground">{fighter.model}</span>
        </p>
        <p className="text-xs text-muted-foreground sm:text-sm">
          harness: <span className="text-foreground">{fighter.harness}</span>
        </p>
      </div>

      <div
        className={cn(
          "rounded-sm border border-border bg-card px-4 py-3 text-[11px] tracking-widest text-muted-foreground",
          align === "right" && "sm:text-right",
        )}
      >
        {fighter.pickups.length ? fighter.pickups.join(" · ") : "NO PICKUPS YET"}
      </div>

      <div className="flex items-center gap-2 rounded-sm border border-border bg-card px-2 py-1.5">
        <Heart className="size-4 shrink-0 fill-hud-green text-hud-green" aria-hidden="true" />
        <div className="h-2.5 w-full overflow-hidden rounded-sm bg-muted">
          <div className="h-full bg-hud-green transition-all" style={{ width: `${healthPct}%` }} />
        </div>
        <span className="shrink-0 font-mono text-xs text-hud-green">
          {fighter.health} / {fighter.maxHealth}
        </span>
      </div>

      <div className={cn("relative aspect-4/3 overflow-hidden rounded-sm border-2", accentBorder)}>
        <img
          src={assetPath(fighter.imageSrc || "/placeholder.svg")}
          alt={`First-person DOOM gameplay view from ${fighter.callsign}'s perspective`}
          className="size-full object-cover"
        />
        <div className="absolute inset-x-0 top-3 flex justify-center px-3">
          <span className="rounded-sm border border-border bg-background/85 px-3 py-1.5 text-center text-[11px] leading-snug text-foreground sm:text-xs">
            {fighter.latestDecision}
          </span>
        </div>
      </div>

      <div className="rounded-sm border-l-2 border-hud-green bg-card px-4 py-3">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[10px] tracking-[0.2em] text-muted-foreground">LATEST DECISION</span>
          {fighter.accepted && (
            <span className="flex items-center gap-1 rounded-sm border border-hud-green/40 bg-hud-green/10 px-1.5 py-0.5 text-[10px] tracking-widest text-hud-green">
              <CheckCircle2 className="size-3" aria-hidden="true" />
              ACCEPTED
            </span>
          )}
        </div>
        <p className="text-xs leading-relaxed text-foreground sm:text-sm">{fighter.latestDecision}</p>
      </div>
    </div>
  )
}
