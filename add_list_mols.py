with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/services.py', 'r') as f:
    code = f.read()

list_mols_code = """
def list_molecules(project_id: str,
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
                   offset: int = 0) -> dict:
    with get_db() as conn:
        query = \"\"\"
            SELECT m.*,
                   (SELECT dr.docking_score FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_score,
                   (SELECT dr.result_origin FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_origin,
                   (SELECT dr.receptor FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_receptor,
                   (SELECT ar.admet_risk_level FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_risk_level,
                   (SELECT ar.result_origin FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_origin,
                   (SELECT ar.gi_absorption FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as gi_absorption,
                   (SELECT ar.bbb_permeant FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as bbb_permeant,
                   (SELECT ar.hepatotoxicity FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as hepatotoxicity,
                   (SELECT cs.composite_score FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) as candidate_score,
                   (SELECT cs.rank_position FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) as rank_position,
                   (SELECT cs.tier FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) as candidate_tier
            FROM molecules m
            WHERE m.project_id = :project_id
        \"\"\"
        params = {"project_id": project_id}

        if search:
            query += " AND (m.name LIKE :search OR m.id LIKE :search OR m.smiles LIKE :search OR m.formula LIKE :search)"
            params["search"] = f"%{search}%"
        if lipinski_only:
            query += " AND m.lipinski_pass = 1"
        if min_mw is not None:
            query += " AND m.molecular_weight >= :min_mw"
            params["min_mw"] = min_mw
        if max_mw is not None:
            query += " AND m.molecular_weight <= :max_mw"
            params["max_mw"] = max_mw
        if min_logp is not None:
            query += " AND m.logp >= :min_logp"
            params["min_logp"] = min_logp
        if max_logp is not None:
            query += " AND m.logp <= :max_logp"
            params["max_logp"] = max_logp
        if max_docking is not None:
            query += " AND (SELECT dr.docking_score FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) <= :max_docking"
            params["max_docking"] = max_docking
        if tier and tier != 'All':
            query += " AND (SELECT cs.tier FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) = :tier"
            params["tier"] = tier

        count_query = f"SELECT COUNT(*) as cnt FROM ({query})"
        total_count = conn.execute(count_query, params).fetchone()["cnt"]

        allowed_sorts = {
            "created_at": "m.created_at",
            "name": "m.name",
            "id": "m.id",
            "molecular_weight": "m.molecular_weight",
            "logp": "m.logp",
            "tpsa": "m.tpsa",
            "qed": "m.qed",
            "docking_score": "docking_score",
            "candidate_score": "candidate_score"
        }
        col = allowed_sorts.get(sort_by, "m.created_at")
        direction = "ASC" if sort_order.lower() == "asc" else "DESC"
        query += f" ORDER BY {col} IS NULL, {col} {direction} LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        rows = conn.execute(query, params).fetchall()
        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "molecules": [dict(r) for r in rows]
        }
"""

code = code.replace("def get_molecule_detail(molecule_id: str)", list_mols_code + "\ndef get_molecule_detail(molecule_id: str)")

with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/services.py', 'w') as f:
    f.write(code)

print("Added list_molecules successfully")
