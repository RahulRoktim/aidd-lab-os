# AIDD Lab OS — Artificial Intelligence Drug Discovery Lab Operating System (v1.4.0)

**AIDD Lab OS** is a provenance-tracking computational drug discovery workspace. It separates project management, dataset versioning, decision logging, and candidate ranking from native scientific computation via a dedicated **AIDD Scientific Worker**.

`NATIVE_RUNTIME_VERIFIED` has a narrow meaning: the supported runtime executed the attested native scientific-tool path, produced structurally valid outputs, persisted execution evidence and provenance, and reproduced the tested result according to the defined checks. It does not validate docking accuracy, binding prediction, efficacy, biological validity, production fitness, or security certification. Synthetic docking fixtures are plumbing tests only.

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

| Mode | Scientific Backend | Native Attestation Eligible | Result Origin Tag |
|---|---|---|---|
| `NATIVE` | Attested RDKit native modules / exact trusted AutoDock Vina binary | **YES, when all checks pass** | `COMPUTED` |
| `IMPORT_ONLY` | Structured import from an external laboratory/cluster run | **NO** | `IMPORTED` |
| `DEMO_FALLBACK` | Pure-Python reference engine / fixtures | **NO** | `DEMO` / `SIMULATED` |

---

## 3. Installation & Deployment

### Option A: Docker Compose (Recommended One-Command Startup)
Builds and starts both the main AIDD Lab OS web application and the AIDD Scientific Worker with isolated Conda environments:

```bash
docker compose up --build
```

- **AIDD Lab OS Web App**: `http://localhost:8000`
- **AIDD Scientific Worker**: `http://localhost:8001`
- **Persistent Storage**: Mounted to `aidd-scientific-data` (`/data/jobs`, `/data/artifacts`, and `/data/aidd_lab.db`).

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
  - Native Attested:   True
AutoDock Vina Docking: [READY]
  - Executable Path:   /opt/conda/envs/aidd-worker-env/bin/vina
  - Version:           AutoDock Vina v1.2.5
  - Native Attested:   True

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
5. **Tier 5 (SCIENTIFIC AUDIT)**: 14-stage runtime audit, known-answer descriptor checks (caffeine, aspirin, etc.), locked scientific records, and automated experiment reproduction.
6. **Tier 6 (E2E WORKFLOW)**: Complete computational campaign from raw SMILES ingestion to composite multi-parameter lead candidate selection.

---

## 6. Scientific Reproducibility Model

- **Environment Fingerprint (`environment_sha256`)**: Normalized SHA-256 cryptographic hash of operating system, Python runtime, compiler, RDKit version, Vina version, and library versions.
- **Locked Scientific Experiment Records**: After `is_locked = 1`, a database trigger rejects changes to scientific fields such as parameters, metrics, tooling, status, and dataset references. Notes and reproduction-link fields are the explicitly permitted appendable metadata.
- **Reproducibility Manifests & ZIP Bundles**: Complete export of all datasets, configurations, decision logs, failure records, and artifacts with `checksums.sha256` verification.

## 7. Docker Native Trust Model

The supported native runtime is the repository's `linux-64` Docker worker. Repository-controlled metadata in `aidd_worker/release_attestation.json` pins the base-image digest, exact Conda package records, expected Vina path, and expected Vina executable SHA-256. The image build fails if the installed package or executable differs. Worker readiness and every docking execution independently recheck the canonical path, package record, version banner, and executable hash. `VINA_BIN` can select a candidate for diagnostics, but it cannot change the trusted identity.

For release `aidd-worker-1.4.0-linux-64`, the trusted Vina executable SHA-256 is `04598a43755cd0e258ac62fc88dcd886aaac6a3167b8ff8712ddc4c07090a019`. A matching banner, plausible output, or zero exit code cannot substitute for this release trust anchor.

RDKit attestation is not described as cryptographic module authentication. It requires the pinned Conda package record and version, expected module origin, compiled extension modules, and passing aspirin and caffeine known-answer calculations.
