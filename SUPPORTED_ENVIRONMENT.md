# Supported environment

Local engineering/demo scope tested on Windows with Python 3.12.10, SQLite and browser JavaScript (no Node build pipeline). Native scientific qualification is separately tied to the unchanged aidd_worker/environment.yml and release_attestation.json Linux/Conda runtime. Installing a different RDKit/Vina is not sufficient for native readiness.

From a fresh clone in PowerShell:

```powershell
python -m venv .venv
& .venv/Scripts/python.exe -m pip install -c constraints-windows-py312.txt -r aidd_worker/requirements.txt
& .venv/Scripts/python.exe -m pip check
& .venv/Scripts/python.exe run_tests.py
& .venv/Scripts/python.exe -m uvicorn aidd_worker.main:app --host 127.0.0.1 --port 8001 --workers 1
```

In a second terminal, run `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`. Open http://127.0.0.1:8000. App startup initializes SQLite without demo seeding. Set AIDD_SEED_DEMO=1 only when synthetic demo creation is intentional. Explicit worker DEMO_FALLBACK requests permit simulated plumbing checks; NATIVE RDKit and Vina require release attestation. Read /readiness before requesting computation. The app's default native worker workflow remains blocked on this host; local demonstration output must retain its origin label.

Use absolute AIDD_DB_PATH, AIDD_DATA_DIR, AIDD_WORKER_JOBS_DIR and AIDD_WORKER_ARTIFACTS_DIR to select storage. Keep one process for each service; MAX_CONCURRENT_JOBS bounds executing jobs within the worker (1 to 8, default 2). Capacity exhaustion returns 429 without creating a job. Batches and request bytes are bounded. Cancellation requests are cooperative; long docking may continue until the existing timeout. Clients must inspect status/failures rather than treating HTTP 200 as computation success.

From any directory, invoke this checkout's run_tests.py to run pytest against its tests. Native tests skip when the exact supported runtime is unavailable; skipped is never verified. Unit mocks and portable Python impostors exercise refusal paths only. The fresh Windows constraints are a tested dependency route, not a replacement for the pinned native environment.

For the native container route use `docker compose config --quiet`, `docker compose up --build -d`, then the existing validate_native_runtime.py harness against local ports. Only configuration parsing was verified in this phase: Docker daemon unavailable, so container builds, native app-to-worker execution and container restore are BLOCKED. Ports publish to 127.0.0.1; internal container binds remain 0.0.0.0. Do not change publications to expose these unauthenticated services.

Stop both services before copying the app database and the complete worker data tree together. Restore into a separate directory; inspect /jobs and /readiness and verify artifact hashes. Startup marks RUNNING/QUEUED records failed; retry creates a new job. Corrupt/orphaned manifests stop recovery and preserve evidence. Retain the original tree and inspect the named job before operator repair; never remove evidence merely to make startup pass. A stopped scratch SQLite copy/restore and worker history reload were tested, not destructive power-loss recovery.

Current app API version 1.2.0, worker/API label 1.4.0, and release-attestation build metadata are distinct namespaces. Quote the exact commit and runtime attestation in evidence. The reusable interfaces remain HTTP /jobs, /readiness and attested artifacts; no repository merge or new platform was introduced.
