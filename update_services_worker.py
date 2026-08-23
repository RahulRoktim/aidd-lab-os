import sys

with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/services.py', 'r') as f:
    code = f.read()

# Add worker_client import at top
if 'from app import worker_client' not in code:
    code = 'from app import worker_client\n' + code

# In get_system_environment_info, include worker connection info
old_env_func = """def get_system_environment_info() -> dict:
    engine_status = ScientificEngine.get_engine_status()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "runtime": "AIDD Lab OS Production Scientific Kernel v1.2.0",
        "cheminformatics_engine": engine_status["active_engine"],
        "has_native_rdkit": engine_status["has_rdkit"],
        "rdkit_version": engine_status["rdkit_version"],
        "engine_notice": engine_status["engine_notice"],
        "hardware": "x86_64 High-Performance Compute Cluster"
    }"""

new_env_func = """def get_system_environment_info() -> dict:
    engine_status = ScientificEngine.get_engine_status()
    worker_st = worker_client.get_worker_status()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "runtime": "AIDD Lab OS Production Scientific Kernel v1.3.0",
        "cheminformatics_engine": engine_status["active_engine"],
        "has_native_rdkit": engine_status["has_rdkit"] or (worker_st["connected"] and worker_st["scientific_software"]["rdkit"]["installed"]),
        "rdkit_version": engine_status["rdkit_version"] or (worker_st.get("scientific_software", {}).get("rdkit", {}).get("version")),
        "engine_notice": engine_status["engine_notice"],
        "scientific_worker": {
            "connected": worker_st["connected"],
            "worker_id": worker_st.get("worker_id"),
            "worker_url": worker_st.get("worker_url"),
            "status": worker_st["status"],
            "capabilities": worker_st.get("scientific_software", {})
        },
        "hardware": "x86_64 High-Performance Compute Cluster"
    }"""

if old_env_func in code:
    code = code.replace(old_env_func, new_env_func)

with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/services.py', 'w') as f:
    f.write(code)

print("Updated services.py with worker connection awareness")
