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

source /venv/main/bin/activate

python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
print("device_count:", torch.cuda.device_count())
PY

python -m pip install -U pip wheel setuptools
python -m pip install -r "$APP_DIR/requirements.txt"
python -m pip check

chmod +x "$APP_DIR/onstart.sh" || true