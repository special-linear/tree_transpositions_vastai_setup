#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/workspace/app"
LOG="/workspace/run.log"
WORKER_LOG="/workspace/worker.log"
PIDFILE="/workspace/ddp.pid"
LOCK="/tmp/ddp.lock"

mkdir -p /workspace
touch "$LOG" "$WORKER_LOG"

# This sends output BOTH to Vast's LOG (stdout) AND to /workspace/run.log
exec > >(tee -a "$LOG") 2>&1
set -x
export PYTHONUNBUFFERED=1

echo "[repo onstart] $(date) start"

source /venv/main/bin/activate
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
  nohup python worker.py >>"$WORKER_LOG" 2>&1 &
  echo $! > "$PIDFILE"
  disown

  # quick “did it immediately crash?” check
  sleep 2
  if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[repo onstart] ERROR: worker exited immediately; tailing worker log:"
    tail -n 200 "$WORKER_LOG" || true
    exit 1
  fi
) 9>"$LOCK"

echo "[repo onstart] worker pid=$(cat "$PIDFILE")"
echo "[repo onstart] tailing $WORKER_LOG into main log"
tail -n 50 -F "$WORKER_LOG"