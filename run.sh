#!/usr/bin/env bash
set -e
cd /working_dir/c_1ed089c83162bf3c/aidd_lab_os
export PYTHONPATH=/working_dir/c_1ed089c83162bf3c/aidd_lab_os
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
