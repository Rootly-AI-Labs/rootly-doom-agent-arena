import { assetPath } from "@/lib/asset-path"

export function MatchViewer() {
  return (
    <section id="match" className="border-b border-primary/30 bg-background">
      <div className="mx-auto max-w-[1800px] px-4 pt-16 pb-5 sm:px-6 sm:pt-24">
        <div className="mb-10 text-center">
          <h2 className="font-sans text-3xl tracking-wide sm:text-4xl">
            ASTRA <span className="text-primary">VS</span> SOL
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            A real recorded match from the benchmark, showing each agent&apos;s live view, health, and the reasoning
            behind its latest decision.
          </p>
        </div>
        <div className="aspect-[1905/832] overflow-hidden">
          <img
          src={assetPath("/images/astra-sol-match.png")}
          alt="Recorded Doom Agent Arena match: GPT-6 Astra versus GPT-6 Sol, showing both player views, health, minimap, and latest decisions."
          width={1905}
          height={902}
          className="block h-auto w-full rounded-sm"
          />
        </div>
      </div>
    </section>
  )
}
