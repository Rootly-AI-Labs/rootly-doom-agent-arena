import { assetPath } from "@/lib/asset-path"

export function MatchViewer() {
  return (
    <section id="match" className="border-b border-primary/30 bg-background">
      <div className="mx-auto max-w-[1800px] px-4 pt-16 pb-5 sm:px-6 sm:pt-24">
        <div className="mb-10 text-center">
          <h2 className="font-sans text-3xl tracking-wide sm:text-4xl">
            GPT 6 Astra <span className="text-primary">VS</span> GPT 6.1 Sol
          </h2>
        </div>
        <div className="mx-auto w-3/4">
          <video
            src={assetPath("/videos/astra-sol61-match.mp4")}
            aria-label="Doom Agent Arena match: GPT-6 Astra versus GPT-6.1 Sol"
            controls
            playsInline
            preload="metadata"
            className="block h-auto w-full rounded-sm"
          >
            Your browser does not support embedded video. <a href={assetPath("/videos/astra-sol61-match.mp4")}>Download the match video.</a>
          </video>
        </div>
      </div>
    </section>
  )
}
