#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

.venv/bin/python manage.py runserver 127.0.0.1:8765
