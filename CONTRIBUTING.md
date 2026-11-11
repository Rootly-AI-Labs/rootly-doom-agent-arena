# Contributing

## Toolchains and dependencies

Use Python 3.15 (selected by `.python-version`), uv, Node.js 26 (selected by
`website/.node-version`), and pnpm 12.18.0. Python 3.12 and 3.14 remain covered by
CI. The arena server and MCP processes use only the Python standard library.

From the repository root:

```sh
uv sync --locked --group maps
uv run --locked pytest
uv run --locked ruff check .
uv run --locked --group maps ty check
uv run --locked yamllint .
uv run --locked actionlint
uv run --locked zizmor --offline .github/workflows
uv run --locked shellcheck scripts/*.sh
```

`pyproject.toml` and `uv.lock` replace `requirements.txt`. The default `dev`
group contains tests and quality tools. Install `--group analysis` for figure
generation or `--group maps` for the optional omgifol WAD generation path.
`ty` checks the server, launchers, smoke scripts, and agent plugin runtime.
Ruff also checks tests and current analysis scripts; archived benchmark code is
excluded. The E402 exceptions allow Matplotlib setup before importing pyplot.

Website setup and checks:

```sh
cd website
npx --yes pnpm@12.18.0 install --frozen-lockfile
npx --yes pnpm@12.18.0 check
NEXT_PUBLIC_BASE_PATH=/rootly-doom-agent-arena npx --yes pnpm@12.18.0 build
NEXT_PUBLIC_BASE_PATH=/rootly-doom-agent-arena npx --yes pnpm@12.18.0 verify:export
```

Oxlint covers TypeScript, React hooks, Next.js, and accessibility. Prettier
provides website formatting; use `pnpm format` to apply it. Plain image elements
are allowed for the static export, which does not run an image optimization
server. The existing match recording has no caption track; its exemption is
local to that video. Supplying captions allows that exemption to be removed.

To enable optional local commit hooks after installing pnpm and the website
dependencies:

```sh
uv run --locked pre-commit install
uv run --locked pre-commit run --all-files
```

## CI and dependency maintenance

All jobs use [Blacksmith runners](https://docs.blacksmith.sh/blacksmith-runners/overview).
The Blacksmith GitHub App must have access to this repository. Checks use
2-vCPU Ubuntu 24.04 runners; website builds and CodeQL use 4-vCPU runners.
The standard uv and pnpm caches are enabled, along with Blacksmith Docker layer
caching scoped to `docker/Dockerfile`. GitHub Actions are pinned to commit
SHAs, with minimal permissions, timeouts, and credentials disabled after checkout.

The test workflow runs both Python suites on 3.12, 3.14, and 3.15, compiles the
C intent-parser and autopilot harnesses, validates browser JavaScript syntax,
and builds and smoke-tests Docker, including host-side MCP and result persistence.
The security workflow runs CodeQL and audits all locked dependency groups weekly
and on pull requests. Python advisories fail the audit; website advisories at
moderate severity or above fail it. Low findings remain visible in the output.

Dependabot checks Actions, Python/uv, website packages, and the Docker base
weekly. Compatible package updates are grouped; major updates remain available.
Review the changelog, commit the regenerated lockfile, and require the checks to
pass before merging.

To update dependencies manually:

```sh
uv lock --upgrade
uv sync --locked --group maps
pnpm --dir website update --latest
```

The website has a documented minimatch override while shadcn's ts-morph
dependency requests an affected older major. shadcn is a build dependency for
its Tailwind stylesheet. Its transitive deepmerge advisory
[GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4) has no
patched upstream release; the audit reports it without ignoring it.

## Runtime and engine verification

```sh
uv run --locked python scripts/smoke_participant_intents_parser.py
uv run --locked python scripts/smoke_participant_autopilot.py
uv run --locked python scripts/smoke_docker_setup.py --port 8010
```

The Docker smoke test creates missing bind-mount files without replacing active
controller tokens. It leaves the container running for inspection; stop it with
`DOOM_ARENA_PORT=8010 docker compose -f docker/docker-compose.yml down`.

Changes to C code still require the Emscripten rebuild described in
[docs/build.md](docs/build.md). CI's native harnesses cover arena logic; a full
browser/WASM duel also requires the browser smoke tests in
[docs/smoke-tests.md](docs/smoke-tests.md).
