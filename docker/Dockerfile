FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY scripts /app/scripts
COPY src /app/src

RUN python -c "\
from pathlib import Path; \
required=[ \
  Path('/app/src/websockets-doom.html'), \
  Path('/app/src/websockets-doom.js'), \
  Path('/app/src/websockets-doom.wasm'), \
  Path('/app/src/default.cfg'), \
  Path('/app/src/doom1-arena.wad'), \
]; \
missing=[str(p) for p in required if not p.exists()]; \
has_iwad=Path('/app/src/doom1.wad').exists() or Path('/app/src/freedoom1.wad').exists(); \
raise SystemExit( \
  ('Missing required runtime asset(s): ' + ', '.join(missing) + \
   '. doom1-arena.wad is the arena WAD built by scripts/generate_duel_room_wad.py; see docs/build.md.') if missing \
  else ('Missing IWAD: provide /app/src/doom1.wad or /app/src/freedoom1.wad.' if not has_iwad else 0) \
)"

RUN mkdir -p /app/benchmarks/results

EXPOSE 8001

CMD ["python", "scripts/doom_arena_server.py", "--host", "0.0.0.0", "--port", "8001"]
