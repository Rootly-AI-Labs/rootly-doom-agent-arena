# Doom Agent Arena website

Static Next.js benchmark website. The actual Doom server remains separate;
GitHub Pages cannot run the Python backend, MCP tools, or live shoutcaster.
Never add API keys or arena controller tokens here.

## Local development

Requires Node.js 24. From this folder:

```powershell
npx --yes pnpm@12.3.4 install --frozen-lockfile
npx --yes pnpm@12.3.4 dev --hostname 127.0.0.1 --port 3000
```

Stop any other server on port 3000 first, or choose another port.
Development uses the root URL when NEXT_PUBLIC_BASE_PATH is unset.

## GitHub Pages

1. Commit and push website/ and .github/workflows/website-pages.yml to main.
2. In the repository, open Settings → Pages → Build and deployment → Source,
   and select GitHub Actions.
3. Run “Website — GitHub Pages” from Actions (or push another website change).
4. After deployment succeeds, visit:
   https://rootly-ai-labs.github.io/rootly-doom-agent-arena/

The workflow checks pull requests without deploying them. Main-branch website
changes build and deploy automatically. Only website/out is published, not
the rest of the arena repository.

## Verify the Pages build locally

```powershell
$env:NEXT_PUBLIC_BASE_PATH = '/rootly-doom-agent-arena'
npx --yes pnpm@12.3.4 build
node scripts/verify-export.mjs
Remove-Item Env:NEXT_PUBLIC_BASE_PATH
```

Output is website/out. Next.js start is not used for a static export.
For a root-level custom domain, change the workflow's NEXT_PUBLIC_BASE_PATH to
an empty string, configure the domain in Pages settings, and rebuild.

## Editing

- Main copy and animations: components/hero.tsx and app/globals.css
- Match screenshot: public/images/astra-sol-match.png
- Current and legacy standings: lib/benchmark-data.ts
- Navigation and methodology link: components/site-header.tsx
- Public asset URLs: use assetPath() from lib/asset-path.ts so subpath hosting works.

The original doom-agent-benchmark-design folder was left intact as a backup.
Make future website changes here.
