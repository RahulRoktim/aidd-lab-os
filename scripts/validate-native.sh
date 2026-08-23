#!/usr/bin/env bash
# ==============================================================================
# AIDD Lab OS — Native Scientific Runtime Validation Runner (Linux/macOS/WSL2)
# Usage: ./scripts/validate-native.sh [--mode AUTO|DOCKER|CONDA|LOCAL] [--cleanup]
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

export PYTHONPATH="$DIR:$PYTHONPATH"

echo "================================================================================"
echo "AIDD LAB OS — LAUNCHING NATIVE SCIENTIFIC VALIDATION HARNESS"
echo "================================================================================"

python3 validate_native_runtime.py "$@"
