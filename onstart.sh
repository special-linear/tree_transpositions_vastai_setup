#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/workspace/app"
LOG="/workspace/run.log"
PIDFILE="/workspace/ddp.pid"
LOCK="/tmp/ddp.lock"

exec >>"$LOG" 2>&1
echo "[repo onstart] $(date) start"


# shellcheck disable=SC1091
source /workspace/.venv/bin/activate
cd "$APP_DIR"

N=$(python - <<'PY'
import torch
print(torch.cuda.device_count())
PY
)

(
  flock -n 9 || exit 0

  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[repo onstart] already running pid=$(cat "$PIDFILE")"
    exit 0
  fi

  echo "[repo onstart] sanity_ddp on $N GPUs"
  torchrun --standalone --nproc_per_node="$N" sanity_ddp.py

  echo "[repo onstart] starting main job"
  nohup torchrun --standalone --nproc_per_node="$N" worker.py &
  echo $! > "$PIDFILE"
  disown
) 9>"$LOCK"