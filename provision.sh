#!/bin/bash
set -euo pipefail

APP_DIR="${APP_DIR:-/workspace/app}"
REPO_URL="${REPO_URL:?set REPO_URL}"

mkdir -p /workspace
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  cd "$APP_DIR" && git pull
fi

# venv in /workspace so it survives restarts of the same instance
python3 -m venv /workspace/.venv || true
source /workspace/.venv/bin/activate
python -m pip install -U pip wheel setuptools
python -m pip install -r "$APP_DIR/requirements.txt"
python -m pip check

install -m 755 "$APP_DIR/onstart.sh" /root/onstart.sh