import { assetPath } from '@/lib/asset-path'
import type { Metadata, Viewport } from 'next'
import { Black_Ops_One, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const blackOpsOne = Black_Ops_One({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-black-ops-one',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
})

export const metadata: Metadata = {
  title: 'Doom Agent Arena — Benchmark Model Duels in DOOM',
  description:
    'Doom Agent Arena is an MCP-native benchmark that pits LLM agents against each other in real-time DOOM duels, scoring win rate, decision speed, accuracy, and damage differential.',
  generator: 'v0.app',
  icons: {
    icon: { url: assetPath('/doom-skull.svg'), type: 'image/svg+xml' },
    shortcut: assetPath('/doom-skull.svg'),
  },
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#0b0b0d',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark bg-background">
      <body className={`${blackOpsOne.variable} ${jetbrainsMono.variable} font-mono antialiased`}>
        {children}
      </body>
    </html>
  )
}
