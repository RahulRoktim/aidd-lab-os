"""Keep test imports and worker jobs away from the operator's database."""
import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="aidd-tests-"))
os.environ["AIDD_DATA_DIR"] = str(_root)
os.environ["AIDD_DB_PATH"] = str(_root / "app.db")
os.environ["AIDD_WORKER_JOBS_DIR"] = str(_root / "jobs")
os.environ["AIDD_WORKER_ARTIFACTS_DIR"] = str(_root / "artifacts")
