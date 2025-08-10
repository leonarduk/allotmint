#!/usr/bin/env bash
set -euo pipefail

# ensure script runs from repository root so log files are written consistently
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load Telegram credentials if available
if [[ -f .env ]]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "Warning: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set; Telegram logging will be disabled." >&2
fi

# ensure config.yaml reflects local environment
python - <<'PY'
import yaml, pathlib
cfg = pathlib.Path('config.yaml')
data = yaml.safe_load(cfg.read_text()) if cfg.exists() else {}
data['env'] = 'local'
cfg.write_text(yaml.safe_dump(data))
PY

uvicorn backend.local_api.main:app \
  --reload \
  --reload-dir backend \
  --port 8000 \
  --log-config backend/logging.ini
