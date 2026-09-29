import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

const prefix = process.env.NEXT_PUBLIC_BASE_PATH || ''
const html = readFileSync('out/index.html', 'utf8')
for (const asset of ['/images/hero-bg.png', '/videos/astra-sol61-match.mp4', '/images/rootly-ai-logo-white.png', '/doom-skull.svg']) {
  assert(html.includes(prefix + asset), 'Missing prefixed asset: ' + asset)
  assert(existsSync(path.join('out', asset)), 'Missing exported asset: ' + asset)
}
for (const match of html.matchAll(/(?:src|href)="(\/[^"]+)"/g)) {
  const url = match[1].replaceAll('&amp;', '&')
  assert(!prefix || url.startsWith(prefix + '/'), 'Unprefixed local URL: ' + url)
  const relative = decodeURIComponent(url.slice(prefix.length).split('?')[0])
  assert(existsSync(path.join('out', relative)), 'Broken exported URL: ' + url)
}
assert(!html.includes('/_vercel/'), 'Vercel-only analytics is not supported on Pages')
console.log('Static export and asset paths verified.')
