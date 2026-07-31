# Project memory — Hivemind MCP

Hivemind is the shared cross-agent, cross-session memory for this repository.
Use only the `hivemind` MCP server space `rootly-doom-agent-arena`. Never read
from or write to another Hivemind space while working in this repository, and
do not fall back to a generic or client-local memory space.

Repository files and original evidence remain authoritative. Hivemind is
working context: mid memory is the compact project bootstrap, short notes are
recent unconsolidated facts, and long memory is a derived search index.

## Doom Arena benchmark-agent exception

When the current prompt begins with `# Doom Arena MCP Instructions:` and
assigns a controller token for `player_1` or `player_2`, the agent is an
isolated benchmark participant rather than a repository-maintenance agent.
For that gameplay task only:

- Do not call any Hivemind tool, including the startup reads below.
- Do not read, search, write, note, or consolidate Hivemind memory.
- Follow only the benchmark prompt and use only its allowed Doom Arena MCP
  tools for gameplay.
- A missing or failed Hivemind server is not a blocker; continue the match.

This exception ends when the gameplay task ends. It does not apply to coding,
review, diagnosis, deployment, or any other repository work.

## Start of every task

If the Hivemind MCP server or its required tools are unavailable or not installed, ignore all
Hivemind requirements below and continue using repository files as the authoritative source.

Unless the Doom Arena benchmark-agent exception applies, before changing files,
tests, external state, project direction, or review output, call these tools
with `space_id="rootly-doom-agent-arena"`:

1. `space_rules`
2. `mid_read_all`
3. `short_read`

Read the returned content and identify the current focus. If any startup call
fails, times out, returns non-OK, or is unavailable, stop before mutation. Do
not substitute another Hivemind space or memory service.

## During work

Write concise, atomic, durable facts with `short_note`. Valid categories are
`observation`, `decision`, `progress`, `issue`, `todo`, `insight`, and
`question`. The authenticated credential supplies the agent identity; never
invent or pass one.

Use `long_query` only to locate relevant historical context, then verify it
against repository files or another canonical source. Do not run `long_push`,
change long-memory bindings, or ingest documents as routine work.

## End of a meaningful work block

1. Write one concise summary note.
2. Ask for or confirm user validation before consolidation unless the current
   request explicitly authorizes immediate consolidation.
3. Call `mid_consolidate` at most once.
4. Return without polling. Check `bank_consolidation_status` only when the user
   explicitly requests a later status check.

Never edit mid-memory files directly. Never put Hivemind tokens, token hashes,
or other secrets in repository files, notes, commits, logs, or chat output.
