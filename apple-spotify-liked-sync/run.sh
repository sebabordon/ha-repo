#!/bin/bash
# Wrapper used by launchd: loads .env and runs the sync.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

exec python3 sync.py "$@"
