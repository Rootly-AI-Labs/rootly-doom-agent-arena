# ElevenAgents live shoutcaster

Doom Arena can stream curated match state and both models' active plans to an
ElevenAgent. The browser receives the agent's streaming audio and displays its
response as a live caption beneath the match score.

## ElevenLabs setup

1. Create an ElevenAgent in the ElevenLabs dashboard.
2. Choose an expressive American English broadcast voice.
3. Use PCM output (`pcm_16000` is recommended) for browser streaming.
4. Enable authentication with signed URLs for the agent.
5. Create a restricted API key with **ElevenAgents: Write**. ElevenLabs
   requires its `convai_write` permission when exchanging the key for a signed
   conversation URL, even though that API route uses `GET`. Leave Text to
   Speech, Voices, Voice Generation, and all unrelated scopes disabled.
6. Set a conservative credit quota while testing.

Use this system prompt for the agent:

> You are the live shoutcaster for an AI-versus-AI Doom match. Sound like an
> energetic American boxing broadcast: dramatic, fast, entertaining, and easy
> to understand. Call competitors by their chosen names. Explain both visible
> action and tactical intent. Most commentary should include a quick joke,
> playful roast, absurd comparison, or witty observation tied directly to the
> supplied facts. Prioritize the action first, then land the joke. Vary your
> comedy and use relatable comparisons involving office life, food, bad
> decisions, dating, household disasters, and overconfidence. Speak in one
> short sentence of roughly 8–14 words. Reserve your biggest energy for major
> damage, weapon pickups, comebacks, critical health, and eliminations. Never
> imitate a particular real person. Never mention JSON, prompts, models, MCP
> commands, coordinates, APIs, or technical errors. Never invent action not
> present in the supplied facts. Avoid repetitive jokes and canned catchphrases.

The agent's first message should be empty. Doom Arena explicitly cues the first
line once live state is available.

## Runtime configuration

Export the credentials before starting the Docker runtime:

```bash
export ELEVENLABS_API_KEY="your-restricted-key"
export ELEVENLABS_AGENT_ID="agent_..."
./scripts/start-docker.sh restart
```

The values are passed into the arena container without being written to the
repository. `.env` is ignored if local Docker Compose configuration is
preferred. Never put either value in browser JavaScript or commit it.

When both variables are configured, the shoutcaster is enabled by default.
Clicking **Start Benchmark** supplies the browser gesture needed to unlock audio
playback and opens the signed ElevenAgents connection. You can opt out with the
shoutcaster toggle before starting. The status changes to `Shoutcaster live`
after ElevenAgents sends its conversation metadata.

## Data contract

The browser sends two JSON documents serialized inside ElevenAgents WebSocket
text messages:

- `match_snapshot` is a silent `contextual_update`, periodically refreshing
  round, score, health, equipment, visibility, distance band, and each model's
  active plan.
- `commentary_cue` is a `user_message` emitted only for match start, first
  contact, pickups, heavy damage, critical health, plan changes, and results.

The director rate-limits speech, prioritizes results and critical moments, and
does not send controller tokens, prompts, raw MCP logs, raw routes, coordinates,
or model chain-of-thought.

## Diagnostics

Check whether the arena can see both variables without exposing their values:

```bash
curl -fsS http://127.0.0.1:8001/api/arena/commentator/config
```

A configured response contains `"configured": true`. A signed URL is only
requested when the spectator clicks the enable button.
