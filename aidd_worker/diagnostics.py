"""
AIDD Worker - Command-Line System Diagnostics Tool
Usage: python3 -m aidd_worker.diagnostics
"""

import sys
import os

from aidd_worker import config
from aidd_worker.services.capability_service import get_all_capabilities
from aidd_worker.services.environment_service import capture_full_environment

def run_diagnostics():
    print("=" * 80)
    print("AIDD SCIENTIFIC WORKER — SYSTEM DIAGNOSTICS")
    print("=" * 80)

    caps = get_all_capabilities()
    env = capture_full_environment()

    print(f"Worker Version:        v{config.WORKER_VERSION}")
    print(f"API Version:           {config.API_VERSION}")
    print(f"Worker Instance ID:    {config.WORKER_ID}")
    print(f"Worker Hostname:       {caps['platform']['hostname']}")
    print(f"Operating System:      {caps['platform']['system']} {caps['platform']['release']} ({caps['platform']['architecture']})")
    print(f"Python Version:        {caps['platform']['python_version']}")
    print(f"CPU Cores Available:   {caps['platform']['cpu_count']}")
    print(f"Configured Port:       {config.PORT} (Host: {config.HOST})")

    print("\n--- SCIENTIFIC SOFTWARE READINESS ---")
    rdkit_st = caps["scientific_software"]["rdkit"]
    print(f"RDKit Cheminformatics: {'[READY]' if rdkit_st['installed'] else '[NOT INSTALLED / FALLBACK]'}")
    print(f"  - Version:           {rdkit_st['version'] or 'N/A'}")
    print(f"  - Backend:           {rdkit_st['backend']}")
    print(f"  - Production Ready:  {rdkit_st['production_ready']}")

    vina_st = caps["scientific_software"]["autodock_vina"]
    print(f"AutoDock Vina Docking: {'[READY]' if vina_st['installed'] else '[NOT DETECTED]'}")
    print(f"  - Executable Path:   {vina_st['path'] or 'None'}")
    print(f"  - Version:           {vina_st['version'] or 'N/A'}")
    print(f"  - Production Ready:  {vina_st['production_ready']}")

    obabel_st = caps["scientific_software"]["openbabel"]
    print(f"OpenBabel Utility:     {'[READY]' if obabel_st['installed'] else '[NOT DETECTED]'}")
    print(f"  - Path:              {obabel_st['path'] or 'None'}")
    print(f"  - Version:           {obabel_st['version'] or 'N/A'}")

    print("\n--- PERSISTENT STORAGE PATHS ---")
    jobs_writable = os.access(config.JOBS_DIR, os.W_OK)
    arts_writable = os.access(config.ARTIFACTS_DIR, os.W_OK)
    print(f"Jobs Directory:        {config.JOBS_DIR} [{'WRITABLE' if jobs_writable else 'READ-ONLY/UNWRITABLE'}]")
    print(f"Artifacts Directory:   {config.ARTIFACTS_DIR} [{'WRITABLE' if arts_writable else 'READ-ONLY/UNWRITABLE'}]")

    print("\n--- SCIENTIFIC ENVIRONMENT FINGERPRINT ---")
    print(f"Environment SHA-256:   {env['environment_sha256']}")

    print("=" * 80)

if __name__ == "__main__":
    run_diagnostics()
