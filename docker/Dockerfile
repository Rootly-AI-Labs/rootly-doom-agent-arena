FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY scripts /app/scripts
COPY src /app/src

RUN python -c "from pathlib import Path; required=[Path('/app/src/websockets-doom.html'), Path('/app/src/websockets-doom.js'), Path('/app/src/websockets-doom.wasm'), Path('/app/src/default.cfg')]; missing=[str(p) for p in required if not p.exists()]; has_iwad=Path('/app/src/doom1.wad').exists() or Path('/app/src/freedoom1.wad').exists(); raise SystemExit(('Missing required runtime asset(s): ' + ', '.join(missing) + '. Rebuild the browser bundle first and provide an IWAD; see docs/build.md.') if missing else ('Missing IWAD: provide /app/src/doom1.wad or /app/src/freedoom1.wad.' if not has_iwad else 0))"

RUN mkdir -p /app/benchmarks/results

EXPOSE 8001

CMD ["python", "scripts/doom_arena_server.py", "--host", "0.0.0.0", "--port", "8001"]
