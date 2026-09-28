import { Hero } from "@/components/hero"
import { Leaderboard } from "@/components/leaderboard"
import { MatchViewer } from "@/components/match-viewer"
import { SiteFooter } from "@/components/site-footer"
import { SiteHeader } from "@/components/site-header"

export default function Page() {
  return (
    <main>
      <SiteHeader />
      <Hero />
      <MatchViewer />
      <Leaderboard />
      <SiteFooter />
    </main>
  )
}
