const pickupDots = [
  { top: "18%", left: "22%" },
  { top: "18%", left: "78%" },
  { top: "42%", left: "38%" },
  { top: "42%", left: "62%" },
  { top: "68%", left: "22%" },
  { top: "68%", left: "78%" },
]

const weaponDots = [
  { top: "8%", left: "50%" },
  { top: "78%", left: "50%" },
]

export function ArenaMinimap() {
  return (
    <div className="relative aspect-square w-full overflow-hidden rounded-sm border border-hud-green/30 bg-background/60">
      <div
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            "linear-gradient(oklch(0.75 0.24 142 / 25%) 1px, transparent 1px), linear-gradient(90deg, oklch(0.75 0.24 142 / 25%) 1px, transparent 1px)",
          backgroundSize: "10% 10%",
        }}
      />
      <div className="absolute left-[15%] top-[10%] h-px w-[30%] bg-hud-green/70" />
      <div className="absolute right-[20%] bottom-[12%] h-[35%] w-px bg-primary/70" />

      {pickupDots.map((pos, i) => (
        <span
          key={i}
          className="absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-hud-green bg-hud-green/30"
          style={pos}
          aria-hidden="true"
        />
      ))}
      {weaponDots.map((pos, i) => (
        <span
          key={i}
          className="absolute h-1.5 w-3 -translate-x-1/2 -translate-y-1/2 rounded-[2px] border border-foreground/60 bg-foreground/20"
          style={pos}
          aria-hidden="true"
        />
      ))}
    </div>
  )
}
