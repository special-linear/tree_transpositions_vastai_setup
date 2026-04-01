#!/bin/bash
set -euo pipefail

APP_DIR="${APP_DIR:-/workspace/app}"
LOG="${LOG:-/workspace/run.log}"
LOCK="/tmp/ddp.lock"

source /workspace/.venv/bin/activate
cd "$APP_DIR"

# Count GPUs
N=$(python - <<'PY'
import torch
print(torch.cuda.device_count())
PY
)

flock -n "$LOCK" bash -lc '
  if pgrep -f "torchrun .*worker.py" >/dev/null; then
    echo "[onstart] job already running" >> "'"$LOG"'"
    exit 0
  fi

  echo "[onstart] preflight: sanity_ddp on $N GPUs" >> "'"$LOG"'"
  if ! torchrun --standalone --nproc_per_node='"$N"' sanity_ddp.py >> "'"$LOG"'" 2>&1; then
    echo "[onstart] sanity_ddp FAILED; not starting job" >> "'"$LOG"'"
    exit 1
  fi

  echo "[onstart] sanity_ddp OK; starting job" >> "'"$LOG"'"
  nohup torchrun --standalone --nproc_per_node='"$N"' train.py >> "'"$LOG"'" 2>&1 &
  disown
'