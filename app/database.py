"""
AIDD Lab OS - Database Engine & Relational Schema
SQLite relational store with scientific immutability, cryptographic SHA-256 hashes,
result origin tracking, and strict foreign keys.
"""

import sqlite3
import os
import json
from contextlib import contextmanager

_default_data_dir = '/data' if os.path.isdir('/data') else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
DB_PATH = os.environ.get('AIDD_DB_PATH', os.path.join(_default_data_dir, 'aidd_lab.db'))

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    disease_indication TEXT,
    target_protein TEXT,
    hypothesis TEXT,
    current_stage TEXT DEFAULT 'Dataset',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS molecules (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT,
    smiles TEXT NOT NULL,
    original_smiles TEXT NOT NULL,
    standardized_smiles TEXT,
    standardization_notes TEXT,
    canonical_smiles TEXT,
    formula TEXT,
    molecular_weight REAL,
    exact_molecular_weight REAL,
    logp REAL,
    hbd INTEGER,
    hba INTEGER,
    tpsa REAL,
    rotatable_bonds INTEGER,
    heavy_atoms INTEGER,
    num_rings INTEGER,
    lipinski_violations INTEGER,
    lipinski_pass INTEGER,
    veber_pass INTEGER,
    qed REAL,
    sas_score REAL,
    fingerprint_bits TEXT,
    svg_structure TEXT,
    descriptor_origin TEXT DEFAULT 'COMPUTED',
    sha256_hash TEXT,
    status TEXT DEFAULT 'active',
    tier TEXT DEFAULT 'Unassigned',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    version_label TEXT NOT NULL,
    parent_dataset_id TEXT,
    experiment_id TEXT,
    description TEXT,
    stage TEXT NOT NULL,
    molecule_count INTEGER DEFAULT 0,
    sha256_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_dataset_id) REFERENCES datasets(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS dataset_molecules (
    dataset_id TEXT NOT NULL,
    molecule_id TEXT NOT NULL,
    included_at TEXT NOT NULL,
    PRIMARY KEY (dataset_id, molecule_id),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (molecule_id) REFERENCES molecules(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    experiment_type TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    input_dataset_id TEXT,
    output_dataset_id TEXT,
    tool TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    molecules_in INTEGER DEFAULT 0,
    molecules_out INTEGER DEFAULT 0,
    molecules_failed INTEGER DEFAULT 0,
    is_locked INTEGER DEFAULT 1,
    reproduction_of_id TEXT,
    reproduction_match INTEGER,
    environment_info TEXT,
    parameters TEXT,
    metrics TEXT,
    logs TEXT,
    warnings TEXT,
    notes TEXT,
    notes_log TEXT,
    reproducibility_manifest TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (input_dataset_id) REFERENCES datasets(id) ON DELETE SET NULL,
    FOREIGN KEY (output_dataset_id) REFERENCES datasets(id) ON DELETE SET NULL,
    FOREIGN KEY (reproduction_of_id) REFERENCES experiments(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS experiment_artifacts (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size_bytes INTEGER DEFAULT 0,
    sha256_hash TEXT NOT NULL,
    file_path TEXT,
    content_preview TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS experiment_failures (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    molecule_id TEXT,
    molecule_name TEXT,
    smiles TEXT,
    pipeline_stage TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS docking_results (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    molecule_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    docking_score REAL NOT NULL,
    result_origin TEXT NOT NULL DEFAULT 'IMPORTED',
    receptor TEXT NOT NULL,
    docking_tool TEXT NOT NULL,
    pose_identifier TEXT,
    binding_site_coords TEXT,
    center_x REAL,
    center_y REAL,
    center_z REAL,
    size_x REAL,
    size_y REAL,
    size_z REAL,
    exhaustiveness INTEGER,
    seed INTEGER,
    vina_version TEXT,
    receptor_file_hash TEXT,
    ligand_file_hash TEXT,
    rmsd_lower_bound REAL DEFAULT 0.0,
    rmsd_upper_bound REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (molecule_id) REFERENCES molecules(id) ON DELETE CASCADE,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admet_results (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    molecule_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    result_origin TEXT NOT NULL DEFAULT 'IMPORTED',
    provider_tool TEXT,
    model_version TEXT,
    endpoint_name TEXT,
    confidence_score REAL,
    units TEXT,
    source_file_hash TEXT,
    gi_absorption TEXT,
    bbb_permeant TEXT,
    cyp3a4_inhibitor TEXT,
    cyp2d6_inhibitor TEXT,
    hepatotoxicity TEXT,
    mutagenicity_ames TEXT,
    herg_inhibition TEXT,
    clearance_rate REAL,
    bioavailability_score REAL,
    admet_risk_level TEXT NOT NULL,
    risk_details TEXT,
    disclaimer TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (molecule_id) REFERENCES molecules(id) ON DELETE CASCADE,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS candidate_scores (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    molecule_id TEXT NOT NULL,
    experiment_id TEXT,
    composite_score REAL NOT NULL,
    result_origin TEXT NOT NULL DEFAULT 'COMPUTED',
    docking_component REAL DEFAULT 0.0,
    qsar_component REAL DEFAULT 0.0,
    admet_component REAL DEFAULT 0.0,
    druglikeness_component REAL DEFAULT 0.0,
    weights_applied TEXT,
    formula_expression TEXT,
    normalization_method TEXT,
    raw_components_json TEXT,
    weighted_components_json TEXT,
    missing_data_policy TEXT DEFAULT 'RENORMALIZE',
    is_data_complete INTEGER DEFAULT 1,
    rank_position INTEGER,
    tier TEXT DEFAULT 'Candidate',
    selection_notes TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (molecule_id) REFERENCES molecules(id) ON DELETE CASCADE,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE SET NULL
);


    CREATE TABLE IF NOT EXISTS scientific_jobs (
        id TEXT PRIMARY KEY,
        experiment_id TEXT,
        job_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        worker_id TEXT,
        tool TEXT,
        tool_version TEXT,
        input_artifacts_json TEXT,
        parameters_json TEXT,
        metrics_json TEXT,
        stdout TEXT,
        stderr TEXT,
        exit_code INTEGER DEFAULT NULL,
        output_artifacts_json TEXT,
        failure_reason TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS decision_logs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    decision_text TEXT NOT NULL,
    rationale TEXT NOT NULL,
    author TEXT DEFAULT 'Lead Researcher',
    related_experiment_id TEXT,
    related_dataset_id TEXT,
    stage TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (related_experiment_id) REFERENCES experiments(id) ON DELETE SET NULL,
    FOREIGN KEY (related_dataset_id) REFERENCES datasets(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS provenance_edges (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_molecules_project ON molecules(project_id);
CREATE INDEX IF NOT EXISTS idx_molecules_status ON molecules(status);
CREATE INDEX IF NOT EXISTS idx_datasets_project ON datasets(project_id);
CREATE INDEX IF NOT EXISTS idx_experiments_project ON experiments(project_id);
CREATE INDEX IF NOT EXISTS idx_docking_molecule ON docking_results(molecule_id);
CREATE INDEX IF NOT EXISTS idx_admet_molecule ON admet_results(molecule_id);
CREATE INDEX IF NOT EXISTS idx_candidate_scores_project ON candidate_scores(project_id);
CREATE INDEX IF NOT EXISTS idx_decision_logs_project ON decision_logs(project_id);
CREATE INDEX IF NOT EXISTS idx_provenance_project ON provenance_edges(project_id);
CREATE INDEX IF NOT EXISTS idx_failures_experiment ON experiment_failures(experiment_id);

CREATE TRIGGER IF NOT EXISTS prevent_locked_experiment_scientific_update
BEFORE UPDATE OF
    id, project_id, name, experiment_type, status, stage,
    input_dataset_id, output_dataset_id, tool, tool_version,
    started_at, completed_at, duration_seconds,
    molecules_in, molecules_out, molecules_failed, is_locked,
    environment_info, parameters, metrics, logs, warnings, notes,
    reproducibility_manifest, created_at
ON experiments
WHEN OLD.is_locked = 1
BEGIN
    SELECT RAISE(ABORT, 'locked experiment scientific fields are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_locked_experiment_delete
BEFORE DELETE ON experiments
WHEN OLD.is_locked = 1
BEGIN
    SELECT RAISE(ABORT, 'locked experiments cannot be deleted');
END;
"""


def get_db_connection():
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(force_recreate: bool = False):
    if force_recreate and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
    print(f"AIDD Lab OS database initialized successfully at {DB_PATH}")


if __name__ == "__main__":
    init_db()
