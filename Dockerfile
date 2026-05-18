FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY scripts /app/scripts
COPY src /app/src

RUN python -c "from pathlib import Path; missing=[str(p) for p in [Path('/app/src/websockets-doom.html'), Path('/app/src/websockets-doom.js'), Path('/app/src/websockets-doom.wasm')] if not p.exists()]; raise SystemExit('Missing prebuilt Doom WASM asset(s): ' + ', '.join(missing) if missing else 0)"

RUN mkdir -p /app/benchmarks/results

EXPOSE 8001

CMD ["python", "scripts/doom_arena_server.py", "--host", "0.0.0.0", "--port", "8001"]
