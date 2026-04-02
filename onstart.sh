#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/workspace/app"
LOG="/workspace/run.log"
WORKER_LOG="/workspace/worker.log"
PIDFILE="/workspace/ddp.pid"
LOCK="/tmp/ddp.lock"

# Everything this script prints goes to run.log (and stderr too)
exec >>"$LOG" 2>&1
set -x
echo "[repo onstart] $(date) start"

# Ensure worker log exists so tail -F works
touch "$WORKER_LOG"

source /workspace/.venv/bin/activate
cd "$APP_DIR"

export PYTHONUNBUFFERED=1

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
  nohup torchrun --standalone --nproc_per_node="$N" worker.py >> "$WORKER_LOG" 2>&1 &
  echo $! > "$PIDFILE"
  disown
) 9>"$LOCK"

# Stream worker output into run.log / Vast LOG
echo "[repo onstart] tailing $WORKER_LOG"
tail -n 50 -F "$WORKER_LOG"