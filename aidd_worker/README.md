# AIDD Scientific Worker (v1.3.0)

Dedicated, decoupled local scientific execution service for **AIDD Lab OS**.

## 1. Architectural Purpose
The AIDD Worker is designed to run locally on a researcher's high-performance workstation or compute cluster. It decouples computationally intensive and binary-dependent scientific software (**RDKit**, **AutoDock Vina**, **OpenBabel**) from the web application and UI layer.

```
┌─────────────────────────────────────────────────────────────┐
│                    AIDD Lab OS (Web App)                    │
│      Projects • Datasets • Provenance • UI • Reports        │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP REST (AIDD_WORKER_URL)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 AIDD Scientific Worker API                  │
│       Capability Discovery • Job Queue • Sandboxing         │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
       ┌───────▼────────┐             ┌────────▼────────┐
       │  Native RDKit  │             │  AutoDock Vina  │
       │ Descriptors/Ro5│             │ Receptor/Ligand │
       └────────────────┘             └─────────────────┘
```

## 2. Quickstart & Installation

### Option A: Conda / Mamba Environment (Recommended)
```bash
conda env create -f environment.yml
conda activate aidd-worker-env
./run_worker.sh
```

### Option B: Docker Container
```bash
docker build -t aidd-worker .
docker run -d -p 8001:8001 --name aidd-worker-instance aidd-worker
```

## 3. Configuration Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AIDD_WORKER_PORT` | `8001` | Worker HTTP listening port |
| `AIDD_WORKER_HOST` | `0.0.0.0` | Bind IP address |
| `AIDD_WORKER_ID` | Auto-generated | Unique worker instance identifier |
| `VINA_BIN` | `vina` | Path or command name for AutoDock Vina binary |
| `OBABEL_BIN` | `obabel` | Path for OpenBabel binary |
| `MAX_DOCKING_TIMEOUT` | `600` | Subprocess execution timeout in seconds |

## 4. API Endpoints

- `GET /health`: Health status, active jobs count, and worker metadata.
- `GET /capabilities`: Live detection of installed RDKit, AutoDock Vina, and OpenBabel binaries.
- `GET /environment`: Computational environment metadata (OS, CPU, Python, packages).
- `GET /validation/rdkit`: Automated 55-molecule benchmark regression audit.
- `POST /jobs/descriptors`: Batch calculation of molecular descriptors & Morgan fingerprints.
- `POST /jobs/standardize`: Desalting, charge neutralization, and canonicalization.
- `POST /jobs/docking`: Structure-based molecular docking with AutoDock Vina.
- `GET /jobs/{job_id}`: Poll job status, stdout/stderr, and parsed results.
- `GET /jobs/{job_id}/artifacts/{filename}`: Download generated scientific artifact files.

## 5. Security & Isolation
- **No Arbitrary Shell Execution**: The worker only accepts typed, structured requests.
- **Path Traversal Protection**: All artifact file accesses are sandboxed and validated against `jobs_data/{job_id}/`.
- **Search Box Sanitization**: Vina bounding box coordinates and sizes are strictly validated as non-zero floats.
