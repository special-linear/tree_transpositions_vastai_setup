#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/workspace/app}"
REPO_URL="${REPO_URL:?set REPO_URL}"
GIT_REF="${GIT_REF:-master}"

set -x
echo "PROVISION: REPO_URL=$REPO_URL APP_DIR=$APP_DIR"
ls -la /workspace || true

mkdir -p /workspace


# Clone or update repo
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch --all --tags
  git -C "$APP_DIR" pull --ff-only || true
fi
git -C "$APP_DIR" checkout -f "$GIT_REF" || true

# Venv in /workspace (persists across restarts of the same instance)
python3 -m venv /workspace/.venv || true
# shellcheck disable=SC1091
source /workspace/.venv/bin/activate

python -m pip install -U pip wheel setuptools
python -m pip install -r "$APP_DIR/requirements.txt"
python -m pip check

chmod +x "$APP_DIR/onstart.sh" || true