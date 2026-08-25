# AIDD Lab OS — Artificial Intelligence Drug Discovery Lab Operating System (v1.4.0)

**AIDD Lab OS** is a provenance-tracking computational drug discovery workspace. It separates project management, dataset versioning, decision logging, and candidate ranking from native scientific computation via a dedicated **AIDD Scientific Worker**.

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AIDD Lab OS (Web App & API Server)                       │
│  Projects • Immutable Datasets • Provenance DAG • Decision Log • Candidates │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP REST (AIDD_WORKER_URL: port 8001)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       AIDD Scientific Worker API                            │
│    Capability Discovery • Bounded Queue • Sandbox • SHA-256 Checksums       │
└──────────────────┬───────────────────────────────────┬──────────────────────┘
                   │                                   │
           ┌───────▼────────┐                 ┌────────▼────────┐
           │  Native RDKit  │                 │  AutoDock Vina  │
           │  C++ Binaries  │                 │ Subprocess Core │
           └────────────────┘                 └─────────────────┘
```

- **AIDD Lab OS App (`app/`)**: FastAPI server providing project management, dataset lineage snapshots with SHA-256 hashes, interactive SVG provenance graphs, multi-objective transparent candidate ranking, and reproducibility manifests.
- **AIDD Scientific Worker (`aidd_worker/`)**: Dedicated execution engine that detects and runs native RDKit and AutoDock Vina, managing job queues, output artifacts, and environment fingerprints.

---

## 2. Scientific Execution Modes

The platform strictly categorizes and tracks the origin of every scientific result:

| Mode | Scientific Backend | Production Ready | Result Origin Tag |
|---|---|---|---|
| `NATIVE` | Genuine RDKit C++ / Native AutoDock Vina binary | **YES** | `COMPUTED` |
| `IMPORT_ONLY` | Structured import from verified laboratory/cluster runs | **YES** | `IMPORTED` |
| `DEMO_FALLBACK` | Calibrated pure-Python reference engine / fixtures | **NO (Non-Production)** | `DEMO` / `SIMULATED` |

---

## 3. Installation & Deployment

### Option A: Docker Compose (Recommended One-Command Startup)
Builds and starts both the main AIDD Lab OS web application and the AIDD Scientific Worker with isolated Conda environments:

```bash
docker compose up --build
```

- **AIDD Lab OS Web App**: `http://localhost:8000`
- **AIDD Scientific Worker**: `http://localhost:8001`
- **Persistent Storage**: Mounted to `aidd-scientific-data` volume (`/data/jobs` and `/data/artifacts`).

---

### Option B: Local Conda / Mamba Environment
To run the worker directly on a workstation with native RDKit and AutoDock Vina:

```bash
# 1. Create and activate Conda environment
conda env create -f aidd_worker/environment.yml
conda activate aidd-worker-env

# 2. Run system diagnostics
python3 -m aidd_worker.diagnostics

# 3. Start the worker service
./aidd_worker/run_worker.sh

# 4. In a separate terminal, start the main application
./run.sh
```

---

## 4. System Diagnostics

Verify host readiness and scientific capabilities anytime using the built-in diagnostic CLI:

```bash
python3 -m aidd_worker.diagnostics
```

Example diagnostic output:
```text
================================================================================
AIDD SCIENTIFIC WORKER — SYSTEM DIAGNOSTICS
================================================================================
Worker Version:        v1.4.0
API Version:           v1
Worker Instance ID:    worker_node01_4a8b1c
Operating System:      Linux 6.6.13 (x86_64)
Python Version:        3.11.8
CPU Cores Available:   16

--- SCIENTIFIC SOFTWARE READINESS ---
RDKit Cheminformatics: [READY]
  - Version:           2023.09.5
  - Backend:           C++ Native Extension
  - Production Ready:  True
AutoDock Vina Docking: [READY]
  - Executable Path:   /opt/conda/envs/aidd-worker-env/bin/vina
  - Version:           AutoDock Vina v1.2.5
  - Production Ready:  True

--- SCIENTIFIC ENVIRONMENT FINGERPRINT ---
Environment SHA-256:   28257acbf678cbd591f2f3cc4eb5d64fca9a81fd77693cc3e04b6edd86c34ceb
================================================================================
```

---

## 5. Multi-Tier Test Suite

Run the unified test runner across all 6 verification tiers:

```bash
python3 run_tests.py
```

Test Tiers:
1. **Tier 1 (UNIT)**: Bounding box constraints, search box validation, PDBQT syntax checks, SHA-256 checksums.
2. **Tier 2 (FIXTURE)**: Multi-pose AutoDock Vina log parsing, binding affinity tables, RMSD bounds.
3. **Tier 3 (NATIVE INTEGRATION)**: Real native RDKit and AutoDock Vina subprocess execution (explicitly reports `SKIPPED` if native binaries are not installed).
4. **Tier 4 (WORKER QUEUE)**: Worker health, readiness endpoint, job queue lifecycle, path traversal guards.
5. **Tier 5 (SCIENTIFIC AUDIT)**: 14-stage scientific software audit, reference benchmarks (Caffeine, Aspirin, etc.), experiment immutability, automated experiment reproduction.
6. **Tier 6 (E2E WORKFLOW)**: Complete computational campaign from raw SMILES ingestion to composite multi-parameter lead candidate selection.

---

## 6. Scientific Reproducibility Model

- **Environment Fingerprint (`environment_sha256`)**: Normalized SHA-256 cryptographic hash of operating system, Python runtime, compiler, RDKit version, Vina version, and library versions.
- **Immutable Experiment Snapshots**: Experiments are automatically locked upon completion (`is_locked = 1`). Historical parameters cannot be modified retroactively; additional observations are logged to an append-only notes trail.
- **Reproducibility Manifests & ZIP Bundles**: Complete export of all datasets, configurations, decision logs, failure records, and artifacts with `checksums.sha256` verification.
