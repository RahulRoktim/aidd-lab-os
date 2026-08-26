"""
AIDD Worker - Data Schemas & Job Models (v1.4.0)
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
import re
from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class JobType(str, Enum):
    DESCRIPTORS = "descriptors"
    STANDARDIZE = "standardize"
    DOCKING = "docking"
    FINGERPRINT = "fingerprint"

class ExecutionMode(str, Enum):
    NATIVE = "NATIVE"
    IMPORT_ONLY = "IMPORT_ONLY"
    DEMO_FALLBACK = "DEMO_FALLBACK"

class StandardizationProfile(str, Enum):
    MINIMAL = "MINIMAL"
    DRUG_LIKE = "DRUG_LIKE"
    CUSTOM = "CUSTOM"

class MoleculeInput(BaseModel):
    id: str
    name: Optional[str] = None
    smiles: str

class DescriptorJobRequest(BaseModel):
    molecules: List[MoleculeInput]
    calculate_fingerprints: Optional[bool] = True
    generate_2d_depictions: Optional[bool] = True
    experiment_id: Optional[str] = None
    execution_mode: Optional[ExecutionMode] = ExecutionMode.NATIVE
    metadata: Optional[Dict[str, Any]] = None

class StandardizeJobRequest(BaseModel):
    molecules: List[MoleculeInput]
    profile: Optional[StandardizationProfile] = StandardizationProfile.DRUG_LIKE
    remove_salts: Optional[bool] = True
    neutralize_charges: Optional[bool] = True
    canonicalize_tautomers: Optional[bool] = False
    filter_lipinski: Optional[bool] = False
    max_mw: Optional[float] = 650.0
    max_logp: Optional[float] = 6.8
    experiment_id: Optional[str] = None
    execution_mode: Optional[ExecutionMode] = ExecutionMode.NATIVE
    metadata: Optional[Dict[str, Any]] = None

class SearchBoxConfig(BaseModel):
    center_x: float
    center_y: float
    center_z: float
    size_x: float = Field(default=20.0, gt=0.0)
    size_y: float = Field(default=20.0, gt=0.0)
    size_z: float = Field(default=20.0, gt=0.0)

    @validator("size_x", "size_y", "size_z", allow_reuse=True)
    def validate_sizes(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError(f"Search box size must be greater than 0 Å (got {v})")
        if v > 100.0:
            raise ValueError(f"Search box size cannot exceed 100 Å for targeted docking (got {v})")
        return v

class DockingJobRequest(BaseModel):
    receptor_pdbqt: str
    receptor_name: Optional[str] = "Receptor"
    ligands: List[Dict[str, str]]
    search_box: SearchBoxConfig
    exhaustiveness: Optional[int] = Field(default=16, ge=1, le=128)
    num_modes: Optional[int] = Field(default=9, ge=1, le=100)
    energy_range: Optional[float] = Field(default=3.0, ge=0.5, le=10.0)
    seed: Optional[int] = 42
    cpu: Optional[int] = 0
    experiment_id: Optional[str] = None
    execution_mode: Optional[ExecutionMode] = ExecutionMode.NATIVE
    metadata: Optional[Dict[str, Any]] = None

    @validator("ligands", allow_reuse=True)
    def validate_ligand_identifiers(cls, ligands: List[Dict[str, str]]) -> List[Dict[str, str]]:
        for index, ligand in enumerate(ligands):
            ligand_id = ligand.get("id")
            if not isinstance(ligand_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", ligand_id):
                raise ValueError(
                    f"Ligand at index {index} requires an ID matching [A-Za-z0-9_-]+; "
                    "path separators, dots, whitespace, newlines, and control characters are forbidden"
                )
            if len(ligand_id) > 128:
                raise ValueError(f"Ligand ID at index {index} exceeds 128 characters")
        if len({ligand["id"] for ligand in ligands}) != len(ligands):
            raise ValueError("Ligand IDs must be unique within a docking request")
        return ligands

class ArtifactInfo(BaseModel):
    name: str
    file_type: str
    size_bytes: int
    sha256_hash: str
    url_path: str

class FailureRecord(BaseModel):
    molecule_id: str
    molecule_name: Optional[str] = None
    smiles: Optional[str] = None
    error_type: str
    error_message: str

class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    job_type: str
    experiment_id: Optional[str] = None
    worker_id: str
    worker_version: str = "1.4.0"
    tool: str
    tool_version: str
    production_ready: bool
    execution_mode: str = "NATIVE"
    environment_sha256: str = ""
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    parameters: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}
    successful_count: int = 0
    failed_count: int = 0
    failures: List[FailureRecord] = []
    artifacts: List[ArtifactInfo] = []
    results: Optional[List[Dict[str, Any]]] = None
    stdout: Optional[str] = ""
    stderr: Optional[str] = ""
    exit_code: Optional[int] = None
    failure_reason: Optional[str] = None
    reproducibility_hash: str = ""

class ReadinessResponse(BaseModel):
    status: str  # "READY", "DEGRADED", "UNAVAILABLE"
    health: str  # "OK"
    worker_version: str = "1.4.0"
    worker_id: str
    api_version: str
    rdkit_ready: bool
    rdkit_version: Optional[str] = None
    rdkit_backend: str
    rdkit_module_path: Optional[str] = None
    rdkit_module_origin_verified: bool = False
    rdkit_native_components_verified: bool = False
    rdkit_package_metadata_verified: bool = False
    rdkit_known_answer_verified: bool = False
    rdkit_known_answer_results: List[Dict[str, Any]] = []
    vina_ready: bool
    vina_version: Optional[str] = None
    vina_path: Optional[str] = None
    vina_expected_path: Optional[str] = None
    vina_identity_verified: bool = False
    vina_binary_sha256: Optional[str] = None
    vina_expected_binary_sha256: Optional[str] = None
    vina_binary_digest_verified: bool = False
    vina_path_verified: bool = False
    vina_package_metadata_verified: bool = False
    vina_version_output_sha256: Optional[str] = None
    openbabel_ready: bool
    environment_sha256: str
    diagnostics: Dict[str, Any]
