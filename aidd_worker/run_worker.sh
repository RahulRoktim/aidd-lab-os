#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

export AIDD_WORKER_PORT="${AIDD_WORKER_PORT:-8001}"
export AIDD_WORKER_HOST="${AIDD_WORKER_HOST:-0.0.0.0}"
export PYTHONPATH="$DIR/..:$PYTHONPATH"

echo "================================================================================"
echo "Starting AIDD Scientific Worker Service v1.3.0 on http://${AIDD_WORKER_HOST}:${AIDD_WORKER_PORT}"
echo "================================================================================"

exec python3 -m uvicorn aidd_worker.main:app --host "$AIDD_WORKER_HOST" --port "$AIDD_WORKER_PORT"
