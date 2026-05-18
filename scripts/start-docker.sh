#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PORT="${DOOM_ARENA_PORT:-8001}"
DEV=0
NO_OPEN_BROWSER=0
TIMEOUT_SECONDS=60

while [ "$#" -gt 0 ]; do
  case "$1" in
    --port)
      PORT="${2:?missing value for --port}"
      shift 2
      ;;
    --dev)
      DEV=1
      shift
      ;;
    --no-open-browser)
      NO_OPEN_BROWSER=1
      shift
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="${2:?missing value for --timeout-seconds}"
      shift 2
      ;;
    -h|--help)
      echo "Usage: scripts/start-docker.sh [--port PORT] [--dev] [--no-open-browser] [--timeout-seconds SECONDS]"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker CLI was not found. Install Docker Desktop or Docker Engine, then rerun this script." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is installed, but the Docker daemon is not reachable. Start Docker and try again." >&2
  exit 1
fi

COMPOSE_FILES=(-f docker-compose.yml)
if [ "$DEV" -eq 1 ]; then
  COMPOSE_FILES+=(-f docker-compose.dev.yml)
fi

BASE_URL="http://127.0.0.1:$PORT"
HEALTH_URL="$BASE_URL/api/arena/health"

echo "Starting Doom Arena Docker backend on $BASE_URL ..."
DOOM_ARENA_PORT="$PORT" docker compose "${COMPOSE_FILES[@]}" up -d --build

request_ok() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1
    return $?
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import urllib.request; urllib.request.urlopen('$HEALTH_URL', timeout=2).read()" >/dev/null 2>&1
    return $?
  fi
  echo "ERROR: readiness polling needs curl or python3." >&2
  return 2
}

DEADLINE=$((SECONDS + TIMEOUT_SECONDS))
READY=0
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  if request_ok; then
    READY=1
    break
  fi
  sleep 0.5
done

if [ "$READY" -ne 1 ]; then
  echo "ERROR: Doom Arena did not become ready at $HEALTH_URL within $TIMEOUT_SECONDS seconds." >&2
  echo "" >&2
  echo "Recent arena logs:" >&2
  DOOM_ARENA_PORT="$PORT" docker compose "${COMPOSE_FILES[@]}" logs --tail=80 arena >&2
  exit 1
fi

echo "Doom Arena is ready: $BASE_URL/"
echo "Host-side MCP env: DOOM_ARENA_BASE_URL=$BASE_URL"

if [ "$NO_OPEN_BROWSER" -ne 1 ]; then
  case "$(uname -s)" in
    Darwin)
      open "$BASE_URL/" >/dev/null 2>&1 || echo "Could not open browser automatically. Open $BASE_URL/ manually." >&2
      ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$BASE_URL/" >/dev/null 2>&1 || echo "Could not open browser automatically. Open $BASE_URL/ manually." >&2
      else
        echo "Open $BASE_URL/ in your browser." >&2
      fi
      ;;
    MINGW*|MSYS*|CYGWIN*)
      cmd.exe /c start "" "$BASE_URL/" >/dev/null 2>&1 || echo "Could not open browser automatically. Open $BASE_URL/ manually." >&2
      ;;
    *)
      echo "Open $BASE_URL/ in your browser." >&2
      ;;
  esac
fi
