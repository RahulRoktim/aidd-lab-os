from app import worker_client
"""
AIDD Lab OS - FastAPI Application Server
Serving scientific REST APIs, reproducibility manifests, and desktop-grade web application.
"""

import os
import io
import csv
import json
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response, Query, Body
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.database import init_db
from app import services
from app.scientific_engine import ScientificEngine

init_db()
services.seed_demo_project()

app = FastAPI(
    title="AIDD Lab OS Scientific API",
    description="Scientific Provenance, Validation & Reproducible Workspace for Computational Drug Discovery",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# -------------------------------------------------------------------
# PYDANTIC SCHEMAS
# -------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    disease_indication: Optional[str] = ""
    target_protein: Optional[str] = ""
    hypothesis: Optional[str] = ""

class MoleculeItem(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    smiles: str

class MoleculeImportRequest(BaseModel):
    dataset_name: Optional[str] = None
    molecules: Optional[List[MoleculeItem]] = None
    csv_text: Optional[str] = None
    notes: Optional[str] = ""

class StandardizeRequest(BaseModel):
    input_dataset_id: str
    experiment_name: Optional[str] = "Standardization & Desalting"
    remove_salts: Optional[bool] = True
    neutralize_charges: Optional[bool] = True
    filter_lipinski: Optional[bool] = False
    max_mw: Optional[float] = 650.0
    max_logp: Optional[float] = 6.8
    notes: Optional[str] = ""

class DockingRequest(BaseModel):
    input_dataset_id: str
    experiment_name: Optional[str] = "AutoDock Vina Screen"
    docking_tool: Optional[str] = "AutoDock Vina"
    tool_version: Optional[str] = "1.2.5"
    receptor: Optional[str] = "EGFR Kinase Domain (PDB: 1M17 / 4WKQ)"
    receptor_pdbqt: Optional[str] = None
    prepared_ligands: Optional[list] = None
    num_modes: Optional[int] = 9
    grid_center: Optional[str] = "x=22.0, y=0.5, z=52.8"
    grid_size: Optional[str] = "20 x 20 x 20 Å"
    center_x: Optional[float] = 22.0
    center_y: Optional[float] = 0.5
    center_z: Optional[float] = 52.8
    size_x: Optional[float] = 20.0
    size_y: Optional[float] = 20.0
    size_z: Optional[float] = 20.0
    exhaustiveness: Optional[int] = 16
    seed: Optional[int] = 42
    result_origin: Optional[str] = "IMPORTED"
    custom_scores_csv: Optional[str] = None
    notes: Optional[str] = ""

class ADMETRequest(BaseModel):
    input_dataset_id: str
    experiment_name: Optional[str] = "In Silico ADMET Profiling"
    tool_name: Optional[str] = "SwissADME & pkCSM Engine"
    result_origin: Optional[str] = "IMPORTED"
    custom_admet_csv: Optional[str] = None
    notes: Optional[str] = ""

class CandidateRankRequest(BaseModel):
    input_dataset_id: Optional[str] = None
    weights: Optional[Dict[str, float]] = None
    missing_data_policy: Optional[str] = "RENORMALIZE"
    experiment_name: Optional[str] = "Candidate Multi-Parameter Ranking"
    notes: Optional[str] = ""

class DecisionCreate(BaseModel):
    title: str
    decision_text: str
    rationale: str
    author: Optional[str] = "Lead Researcher"
    related_experiment_id: Optional[str] = None
    related_dataset_id: Optional[str] = None
    stage: Optional[str] = None

class AppendNoteRequest(BaseModel):
    note: str
    author: Optional[str] = "Researcher"

# -------------------------------------------------------------------
# HTML FRONTEND ROUTE
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/projects", response_class=HTMLResponse)
@app.get("/projects/{rest_of_path:path}", response_class=HTMLResponse)
async def serve_spa_frontend(request: Request, rest_of_path: str = ""):
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>AIDD Lab OS</h1><p>Initializing frontend interface...</p>")

# -------------------------------------------------------------------
# REST API: PROJECTS
# -------------------------------------------------------------------

@app.get("/api/projects")
async def get_projects():
    return services.list_projects()

@app.post("/api/projects")
async def create_project(data: ProjectCreate):
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Project name is required")
    return services.create_project(
        name=data.name.strip(),
        description=data.description,
        disease_indication=data.disease_indication,
        target_protein=data.target_protein,
        hypothesis=data.hypothesis
    )

@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    proj = services.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    services.delete_project(project_id)
    return {"status": "deleted", "project_id": project_id}

@app.get("/api/projects/{project_id}/reproducibility-bundle")
async def get_project_bundle(project_id: str):
    try:
        bundle_bytes = services.generate_project_reproducibility_bundle(project_id)
        proj = services.get_project(project_id)
        filename = f"reproducibility_bundle_{proj['name'].replace(' ', '_')}_{project_id}.zip"
        return Response(
            content=bundle_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# -------------------------------------------------------------------
# REST API: MOLECULES & STANDARDIZATION
# -------------------------------------------------------------------

@app.post("/api/projects/{project_id}/molecules/import")
async def import_molecules(project_id: str, payload: MoleculeImportRequest):
    records = []
    if payload.molecules:
        for m in payload.molecules:
            records.append({"id": m.id, "name": m.name, "smiles": m.smiles})
    elif payload.csv_text:
        reader = csv.DictReader(io.StringIO(payload.csv_text.strip()))
        for r in reader:
            records.append({
                "id": r.get("id") or r.get("molecule_id") or r.get("Compound_ID"),
                "name": r.get("name") or r.get("molecule_name") or r.get("Compound_Name"),
                "smiles": r.get("smiles") or r.get("SMILES") or r.get("canonical_smiles")
            })

    if not records:
        raise HTTPException(status_code=400, detail="No molecule records provided in CSV or JSON payload")

    return services.import_molecules_from_csv_or_list(
        project_id=project_id,
        molecule_records=records,
        dataset_name=payload.dataset_name,
        notes=payload.notes or ""
    )

@app.post("/api/projects/{project_id}/molecules/standardize")
async def standardize_dataset(project_id: str, data: StandardizeRequest):
    try:
        return services.run_standardization_experiment(
            project_id=project_id,
            input_dataset_id=data.input_dataset_id,
            experiment_name=data.experiment_name or "Standardization & Desalting",
            remove_salts=data.remove_salts if data.remove_salts is not None else True,
            neutralize_charges=data.neutralize_charges if data.neutralize_charges is not None else True,
            filter_lipinski=data.filter_lipinski if data.filter_lipinski is not None else False,
            max_mw=data.max_mw or 650.0,
            max_logp=data.max_logp or 6.8,
            notes=data.notes or ""
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/projects/{project_id}/molecules")
async def get_molecules(
    project_id: str,
    search: Optional[str] = None,
    stage: Optional[str] = None,
    lipinski_only: bool = False,
    min_mw: Optional[float] = None,
    max_mw: Optional[float] = None,
    min_logp: Optional[float] = None,
    max_logp: Optional[float] = None,
    max_docking: Optional[float] = None,
    tier: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 100,
    offset: int = 0
):
    return services.list_molecules(
        project_id=project_id,
        search=search,
        stage=stage,
        lipinski_only=lipinski_only,
        min_mw=min_mw,
        max_mw=max_mw,
        min_logp=min_logp,
        max_logp=max_logp,
        max_docking=max_docking,
        tier=tier,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset
    )

@app.get("/api/molecules/{molecule_id}")
async def get_molecule_detail(molecule_id: str):
    mol = services.get_molecule_detail(molecule_id)
    if not mol:
        raise HTTPException(status_code=404, detail="Molecule not found")
    return mol

# -------------------------------------------------------------------
# REST API: DATASETS & VERSIONING
# -------------------------------------------------------------------

@app.get("/api/projects/{project_id}/datasets")
async def get_datasets(project_id: str):
    return services.get_project_datasets(project_id)

@app.get("/api/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    ds = services.get_dataset_detail(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds

@app.get("/api/datasets/compare")
async def compare_datasets(id1: str = Query(...), id2: str = Query(...)):
    try:
        return services.compare_datasets(id1, id2)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/datasets/{dataset_id}/export/csv")
async def export_dataset_csv(dataset_id: str):
    try:
        csv_data = services.export_dataset_csv(dataset_id)
        ds = services.get_dataset_detail(dataset_id)
        filename = f"{ds['version_label'] if ds else dataset_id}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# -------------------------------------------------------------------
# REST API: EXPERIMENTS, IMMUTABILITY & REPRODUCTION
# -------------------------------------------------------------------

@app.get("/api/projects/{project_id}/experiments")
async def get_experiments(project_id: str):
    return services.list_experiments(project_id)

@app.get("/api/experiments/{experiment_id}")
async def get_experiment(experiment_id: str):
    exp = services.get_experiment_detail(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp

@app.get("/api/experiments/{experiment_id}/manifest")
async def get_experiment_manifest(experiment_id: str):
    try:
        return services.generate_experiment_manifest(experiment_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/experiments/{experiment_id}/reproduce")
async def reproduce_experiment(experiment_id: str):
    try:
        return services.reproduce_experiment(experiment_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/experiments/{experiment_id}/notes")
async def append_note(experiment_id: str, data: AppendNoteRequest):
    try:
        return services.append_experiment_note(experiment_id, data.note, data.author)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/experiments/{experiment_id}/failures/csv")
async def export_failures_csv(experiment_id: str):
    try:
        csv_data = services.export_failures_csv(experiment_id)
        filename = f"failures_{experiment_id}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/projects/{project_id}/experiments/docking")
async def run_docking(project_id: str, data: DockingRequest):
    try:
        return services.import_or_run_docking(
            project_id=project_id,
            input_dataset_id=data.input_dataset_id,
            experiment_name=data.experiment_name or "AutoDock Vina Screen",
            docking_tool=data.docking_tool or "AutoDock Vina",
            tool_version=data.tool_version or "1.2.5",
            receptor=data.receptor or "EGFR Kinase Domain (PDB: 1M17 / 4WKQ)",
            grid_center=data.grid_center or "x=22.0, y=0.5, z=52.8",
            grid_size=data.grid_size or "20 x 20 x 20 Å",
            center_x=data.center_x or 22.0,
            center_y=data.center_y or 0.5,
            center_z=data.center_z or 52.8,
            size_x=data.size_x or 20.0,
            size_y=data.size_y or 20.0,
            size_z=data.size_z or 20.0,
            exhaustiveness=data.exhaustiveness or 16,
            seed=data.seed or 42,
            result_origin=data.result_origin or "IMPORTED",
            custom_scores_csv=data.custom_scores_csv,
            notes=data.notes or ""
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/projects/{project_id}/experiments/admet")
async def run_admet(project_id: str, data: ADMETRequest):
    try:
        return services.import_or_run_admet(
            project_id=project_id,
            input_dataset_id=data.input_dataset_id,
            experiment_name=data.experiment_name or "In Silico ADMET Profiling",
            tool_name=data.tool_name or "SwissADME & pkCSM Engine",
            result_origin=data.result_origin or "IMPORTED",
            custom_admet_csv=data.custom_admet_csv,
            notes=data.notes or ""
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/projects/{project_id}/experiments/candidates/rank")
async def rank_candidates(project_id: str, data: CandidateRankRequest):
    try:
        return services.calculate_candidate_rankings(
            project_id=project_id,
            input_dataset_id=data.input_dataset_id,
            weights=data.weights,
            missing_data_policy=data.missing_data_policy or "RENORMALIZE",
            experiment_name=data.experiment_name or "Candidate Multi-Parameter Ranking",
            notes=data.notes or ""
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# -------------------------------------------------------------------
# REST API: CANDIDATES
# -------------------------------------------------------------------

@app.get("/api/projects/{project_id}/candidates")
async def get_candidates(project_id: str):
    return services.get_candidate_rankings(project_id)

# -------------------------------------------------------------------
# REST API: DECISIONS
# -------------------------------------------------------------------

@app.get("/api/projects/{project_id}/decisions")
async def get_decisions(project_id: str):
    return services.list_decision_logs(project_id)

@app.post("/api/projects/{project_id}/decisions")
async def add_decision(project_id: str, data: DecisionCreate):
    if not data.title.strip() or not data.decision_text.strip():
        raise HTTPException(status_code=400, detail="Decision title and text are required")
    return services.add_decision_log(
        project_id=project_id,
        title=data.title.strip(),
        decision_text=data.decision_text.strip(),
        rationale=data.rationale.strip(),
        author=data.author or "Lead Researcher",
        related_experiment_id=data.related_experiment_id,
        related_dataset_id=data.related_dataset_id,
        stage=data.stage
    )

@app.delete("/api/decisions/{decision_id}")
async def delete_decision(decision_id: str):
    services.delete_decision_log(decision_id)
    return {"status": "deleted", "decision_id": decision_id}

# -------------------------------------------------------------------
# REST API: PROVENANCE
# -------------------------------------------------------------------

@app.get("/api/projects/{project_id}/provenance")
async def get_provenance(project_id: str):
    return services.get_provenance_graph(project_id)

# -------------------------------------------------------------------
# REST API: REPRODUCIBILITY REPORT
# -------------------------------------------------------------------

@app.get("/api/projects/{project_id}/report")
async def get_report_data(project_id: str, format: str = "json"):
    try:
        report_data = services.generate_reproducibility_report_data(project_id)
        if format.lower() == "html":
            html_content = render_html_report(report_data)
            return HTMLResponse(content=html_content)
        return report_data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def render_html_report(report: dict) -> str:
    p = report["project"]
    env = report["system_environment"]
    datasets = report["datasets"]
    experiments = report["experiments"]
    failures = report["all_failures"]
    decisions = report["decisions"]
    candidates = report["candidates"]

    ds_rows = "".join([
        f"<tr><td><code>{d['version_label']}</code></td><td>{d['name']}</td><td>{d['stage']}</td><td><b>{d['molecule_count']}</b></td><td><code>{d.get('sha256_hash', '')[:12]}...</code></td><td>{d['created_at'][:19]}</td></tr>"
        for d in datasets
    ])

    exp_rows = "".join([
        f"<tr><td><b>{e['name']}</b></td><td><code>{e['tool']} v{e['tool_version']}</code></td><td>{e['stage']}</td><td><span class='badge badge-{e['status']}'>{e['status']}</span></td><td>{e['duration_seconds']}s</td><td>{e['molecules_in']} in / {e['molecules_out']} out</td><td>{e.get('molecules_failed', 0)} failed</td></tr>"
        for e in experiments
    ])

    fail_rows = "".join([
        f"<tr><td><code>{f.get('molecule_id', 'N/A')}</code></td><td>{f.get('molecule_name', 'Unknown')}</td><td><span class='badge badge-fail'>{f['error_type']}</span></td><td>{f['pipeline_stage']}</td><td>{f['error_message']}</td></tr>"
        for f in failures
    ]) if failures else "<tr><td colspan='5' class='text-muted'>No failures recorded across all pipeline stages.</td></tr>"

    dec_rows = "".join([
        f"<div class='decision-card'><div class='decision-header'><b>{d['title']}</b> <span class='badge'>{d.get('stage', 'Stage')}</span> <span class='date'>{d['created_at'][:10]}</span></div><p><b>Decision:</b> {d['decision_text']}</p><p><b>Scientific Rationale:</b> {d['rationale']}</p><p class='meta'><b>Author:</b> {d['author']} | <b>Linked Experiment:</b> {d.get('related_experiment_name', 'None')}</p></div>"
        for d in decisions
    ]) if decisions else "<p class='text-muted'>No research decisions logged yet.</p>"

    cand_rows = "".join([
        f"<tr><td><b>#{c['rank_position']}</b></td><td><b>{c['molecule_name']}</b><br><code>{c['molecule_id']}</code></td><td><span class='badge badge-tier'>{c['tier']}</span></td><td><span class='badge badge-origin'>{c.get('result_origin', 'COMPUTED')}</span></td><td><b>{c['composite_score']:.1f}</b></td><td>{c.get('docking_score', 'N/A')} kcal/mol</td><td>{c.get('admet_risk_level', 'N/A')}</td><td>{c['molecular_weight']} Da</td><td>{c['logp']}</td><td>{c['tpsa']} Å²</td></tr>"
        for c in candidates
    ]) if candidates else "<tr><td colspan='10' class='text-muted'>No candidates ranked yet.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AIDD Lab OS — Reproducibility Report ({p['name']})</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0B0F19; color: #E2E8F0; margin: 0; padding: 40px; line-height: 1.5; }}
        .report-container {{ max-width: 1040px; margin: 0 auto; background: #131A2B; border: 1px solid #1E293B; border-radius: 8px; padding: 40px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        h1, h2, h3, h4 {{ color: #F8FAFC; margin-top: 0; }}
        h1 {{ font-size: 26px; border-bottom: 1px solid #1E293B; padding-bottom: 16px; margin-bottom: 24px; }}
        h2 {{ font-size: 18px; margin-top: 32px; margin-bottom: 14px; border-left: 4px solid #38BDF8; padding-left: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0 24px 0; font-size: 13px; }}
        th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #1E293B; }}
        th {{ background: #0F172A; color: #94A3B8; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; }}
        tr:hover {{ background: rgba(255,255,255,0.02); }}
        code {{ background: #0F172A; padding: 2px 6px; border-radius: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; color: #38BDF8; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; background: #334155; color: #E2E8F0; }}
        .badge-completed {{ background: #064E3B; color: #34D399; }}
        .badge-failed, .badge-fail {{ background: #7F1D1D; color: #F87171; }}
        .badge-tier {{ background: #1E3A8A; color: #60A5FA; }}
        .badge-origin {{ background: #4C1D95; color: #C4B5FD; }}
        .decision-card {{ background: #0F172A; border: 1px solid #1E293B; border-radius: 6px; padding: 16px; margin-bottom: 12px; font-size: 13px; }}
        .decision-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid #1E293B; padding-bottom: 6px; }}
        .meta {{ font-size: 11px; color: #64748B; margin-top: 8px; }}
        .callout {{ background: #0F172A; border-left: 4px solid #38BDF8; padding: 14px 16px; border-radius: 0 6px 6px 0; margin: 16px 0; font-size: 13px; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .stat-box {{ background: #0F172A; border: 1px solid #1E293B; border-radius: 6px; padding: 16px; }}
        .stat-val {{ font-size: 22px; font-weight: 700; color: #38BDF8; margin-top: 4px; }}
        .text-muted {{ color: #64748B; font-style: italic; }}
    </style>
</head>
<body>
    <div class="report-container">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
            <div>
                <span style="font-size: 12px; font-weight: 700; color: #38BDF8; letter-spacing: 0.1em; text-transform: uppercase;">AIDD Lab OS • Scientific Reproducibility Audit</span>
                <h1 style="margin-top: 6px;">{p['name']}</h1>
            </div>
            <div style="text-align: right; font-size: 12px; color: #64748B;">
                Generated: {report['generated_at'][:19].replace('T', ' ')} UTC<br>
                Project ID: <code>{p['id']}</code>
            </div>
        </div>

        <div class="callout">
            <b>Research Objective & Hypothesis:</b><br>
            {p.get('hypothesis') or 'No explicit hypothesis logged.'}
        </div>

        <div class="grid-2" style="margin-bottom: 24px;">
            <div class="stat-box">
                <div style="font-size: 11px; color: #94A3B8; text-transform: uppercase; font-weight: 600;">Biological Target</div>
                <div style="font-size: 14px; font-weight: 600; color: #F1F5F9; margin-top: 4px;">{p.get('target_protein', 'N/A')}</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Indication: {p.get('disease_indication', 'N/A')}</div>
            </div>
            <div class="stat-box">
                <div style="font-size: 11px; color: #94A3B8; text-transform: uppercase; font-weight: 600;">Reproducibility Environment</div>
                <div style="font-size: 12px; color: #CBD5E1; margin-top: 4px;">OS: {env['os']} ({env['architecture']})</div>
                <div style="font-size: 12px; color: #CBD5E1;">Engine: {env['cheminformatics_engine']}</div>
            </div>
        </div>

        <h2>1. Dataset Versioning & Lineage (Cryptographic SHA-256 Checksums)</h2>
        <table>
            <thead>
                <tr><th>Version</th><th>Dataset Name</th><th>Stage</th><th>Compounds</th><th>SHA-256 Checksum</th><th>Timestamp</th></tr>
            </thead>
            <tbody>
                {ds_rows}
            </tbody>
        </table>

        <h2>2. Computational Experiment Execution Audit</h2>
        <table>
            <thead>
                <tr><th>Experiment</th><th>Tool & Version</th><th>Stage</th><th>Status</th><th>Duration</th><th>Throughput</th><th>Failures</th></tr>
            </thead>
            <tbody>
                {exp_rows}
            </tbody>
        </table>

        <h2>3. Scientific Failure & Exclusion Log</h2>
        <table>
            <thead>
                <tr><th>Molecule ID</th><th>Name / Identifier</th><th>Error Type</th><th>Stage</th><th>Detailed Scientific Reason</th></tr>
            </thead>
            <tbody>
                {fail_rows}
            </tbody>
        </table>

        <h2>4. Research Decision Log & Rationale</h2>
        {dec_rows}

        <h2>5. Top Ranked Drug Candidates (Scientific Origin Tracked)</h2>
        <table>
            <thead>
                <tr><th>Rank</th><th>Candidate Name</th><th>Tier</th><th>Origin</th><th>Composite Score</th><th>Docking Affinity</th><th>ADMET Safety</th><th>MW</th><th>LogP</th><th>TPSA</th></tr>
            </thead>
            <tbody>
                {cand_rows}
            </tbody>
        </table>

        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #1E293B; font-size: 11px; color: #64748B; text-align: center;">
            AIDD Lab OS — Provenance & Reproducibility Certified. All experimental parameters, datasets, and decision trails are cryptographically and relationally traceable.
        </div>
    </div>
</body>
</html>"""

# -------------------------------------------------------------------
# SCIENTIFIC AUDIT & REVIEWS
# -------------------------------------------------------------------

@app.get("/api/scientific/status")
async def get_scientific_status():
    return ScientificEngine.get_engine_status()

@app.get("/api/scientific/audit")
async def run_scientific_audit():
    return ScientificEngine.run_regression_audit()

@app.post("/api/chem/parse")
async def live_chem_parse(payload: Dict[str, str] = Body(...)):
    smiles = payload.get("smiles", "")
    desc = ScientificEngine.calculate_descriptors(smiles)
    if desc["valid"]:
        desc["svg"] = ScientificEngine.generate_2d_structure(smiles, width=280, height=200, dark_mode=True)
        desc["fingerprint"] = ScientificEngine.generate_fingerprint(smiles)
    return desc

@app.post("/api/demo/reset")
async def reset_demo_project():
    init_db(force_recreate=True)
    services.seed_demo_project()
    return {"status": "seeded", "project": services.get_project("proj_egfr_demo")}

# -------------------------------------------------------------------
# REST API: SCIENTIFIC WORKER CONNECTION & JOBS
# -------------------------------------------------------------------

@app.get("/api/worker/status")
async def get_worker_status_endpoint():
    return worker_client.get_worker_status()

@app.get("/api/worker/validation/rdkit")
async def get_worker_rdkit_validation():
    success, res = worker_client.run_worker_rdkit_validation()
    if not success:
        raise HTTPException(status_code=503, detail=f"Scientific worker offline: {res}")
    return res

@app.post("/api/worker/jobs/descriptors")
async def proxy_worker_descriptors(payload: Dict[str, Any] = Body(...)):
    mols = payload.get("molecules", [])
    success, res = worker_client.submit_descriptor_job(mols, payload.get("experiment_id"))
    if not success:
        raise HTTPException(status_code=503, detail=f"Worker error: {res}")
    return res

@app.post("/api/worker/jobs/docking")
async def proxy_worker_docking(payload: Dict[str, Any] = Body(...)):
    success, res = worker_client.submit_docking_job(
        receptor_pdbqt=payload.get("receptor_pdbqt", ""),
        ligands=payload.get("ligands", []),
        search_box=payload.get("search_box", {}),
        exhaustiveness=payload.get("exhaustiveness", 16),
        num_modes=payload.get("num_modes", 9),
        seed=payload.get("seed", 42),
        experiment_id=payload.get("experiment_id")
    )
    if not success:
        raise HTTPException(status_code=503, detail=f"Worker error: {res}")
    return res

@app.get("/api/worker/jobs/{job_id}")
async def proxy_get_job(job_id: str):
    success, res = worker_client.get_job_status(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job not found or worker unreachable: {res}")
    return res

@app.get("/api/worker/readiness")
async def get_worker_readiness_endpoint():
    success, res = worker_client.get_worker_readiness()
    if not success:
        return {"status": "UNAVAILABLE", "health": "OFFLINE", "error": str(res)}
    return res

@app.get("/api/worker/environment")
async def get_worker_environment_endpoint():
    success, res = worker_client.get_worker_environment()
    if not success:
        return {"status": "UNAVAILABLE", "error": str(res)}
    return res

@app.post("/api/worker/cancel/{job_id}")
async def cancel_worker_job_endpoint(job_id: str):
    success, res = worker_client.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to cancel job: {res}")
    return res
