with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/services.py', 'r') as f:
    code = f.read()

# Update signature
old_sig = """def calculate_candidate_rankings(project_id: str,
                                 weights: Optional[Dict[str, float]] = None,
                                 missing_data_policy: str = "RENORMALIZE",
                                 experiment_name: str = "Candidate Multi-Parameter Ranking",
                                 notes: str = "") -> dict:"""

new_sig = """def calculate_candidate_rankings(project_id: str,
                                 input_dataset_id: Optional[str] = None,
                                 weights: Optional[Dict[str, float]] = None,
                                 missing_data_policy: str = "RENORMALIZE",
                                 experiment_name: str = "Candidate Multi-Parameter Ranking",
                                 notes: str = "") -> dict:"""

if old_sig in code:
    code = code.replace(old_sig, new_sig)

# Update reproduction call
old_rep = """    elif exp_type == "candidate_ranking":
        new_exp_res = calculate_candidate_rankings(
            project_id=project_id,
            weights=params.get("weights"),
            missing_data_policy=params.get("missing_data_policy", "RENORMALIZE"),
            experiment_name=new_name,
            notes=f"Reproduced from experiment {experiment_id}"
        )"""

new_rep = """    elif exp_type == "candidate_ranking":
        new_exp_res = calculate_candidate_rankings(
            project_id=project_id,
            input_dataset_id=in_ds_id,
            weights=params.get("weights"),
            missing_data_policy=params.get("missing_data_policy", "RENORMALIZE"),
            experiment_name=new_name,
            notes=f"Reproduced from experiment {experiment_id}"
        )"""

if old_rep in code:
    code = code.replace(old_rep, new_rep)

# In calculate_candidate_rankings, insert input_dataset_id into experiment record
code = code.replace(
    """            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, ?, 'candidate_ranking', 'completed', 'Candidate Selection', NULL, NULL, 'AIDD Multi-Objective Optimizer', '1.2.0', ?, ?, ?, ?, ?, 0, 1, NULL, NULL, ?, ?, ?, ?, '', ?, '[]', '', ?)""",
    """            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, ?, 'candidate_ranking', 'completed', 'Candidate Selection', ?, NULL, 'AIDD Multi-Objective Optimizer', '1.2.0', ?, ?, ?, ?, ?, 0, 1, NULL, NULL, ?, ?, ?, ?, '', ?, '[]', '', ?)"""
)

# And add input_dataset_id to execute tuple for candidate_ranking
code = code.replace(
    """            (
                exp_id, project_id, experiment_name,
                start_ts, end_ts, duration, len(scores_list), len(scores_list),""",
    """            (
                exp_id, project_id, experiment_name, input_dataset_id,
                start_ts, end_ts, duration, len(scores_list), len(scores_list),"""
)

with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/services.py', 'w') as f:
    f.write(code)

print("services.py updated successfully")
