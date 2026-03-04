#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

HOST="${APP_HOST:-${HOST:-127.0.0.1}}"
START_PORT="${APP_PORT:-${PORT:-8000}}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

FREE_PORT="$($PYTHON_BIN - "$HOST" "$START_PORT" <<'PY'
import socket
import sys

host = sys.argv[1]
start = int(sys.argv[2])

for port in range(start, start + 200):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            print(port)
            break
        except OSError:
            continue
else:
    raise SystemExit("No free port found in checked range")
PY
)"

echo "Starting API server on http://${HOST}:${FREE_PORT}"
echo "UI:      http://${HOST}:${FREE_PORT}/"
echo "Health:  http://${HOST}:${FREE_PORT}/health"
echo "Groq:    http://${HOST}:${FREE_PORT}/health/groq"
echo "Chat:    http://${HOST}:${FREE_PORT}/chat"
echo "Stream:  http://${HOST}:${FREE_PORT}/chat/stream"

exec "$PYTHON_BIN" -m uvicorn api_server:app --host "$HOST" --port "$FREE_PORT"
