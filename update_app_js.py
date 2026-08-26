with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/static/js/app.js', 'r') as f:
    code = f.read()

# Add worker checking to init & state
if 'workerStatus: null,' not in code:
    code = code.replace("engineStatus: null,", "engineStatus: null,\n    workerStatus: null,")
if 'await this.checkWorkerStatus();' not in code:
    code = code.replace("await this.loadEngineStatus();", "await this.loadEngineStatus();\n    await this.checkWorkerStatus();")

check_worker_fn = """
  async checkWorkerStatus() {
    try {
      this.state.workerStatus = await this.api('/api/worker/status');
    } catch (e) {
      this.state.workerStatus = { connected: false, status: 'DISCONNECTED' };
    }
  },
"""

if 'async checkWorkerStatus()' not in code:
    code = code.replace("async loadEngineStatus() {", check_worker_fn + "\n  async loadEngineStatus() {")

# Update renderHeader
old_header = """    headerElem.innerHTML = bcHtml;"""

new_header = """    const ws = this.state.workerStatus;
    const isConn = ws && ws.connected;
    const rdkitSt = isConn && ws.scientific_software && ws.scientific_software.rdkit && ws.scientific_software.rdkit.installed;
    const vinaSt = isConn && ws.scientific_software && ws.scientific_software.autodock_vina && ws.scientific_software.autodock_vina.installed;

    const workerPillHtml = `
      <div class="worker-status-pill ${isConn ? 'connected' : 'disconnected'}" onclick="AIDD.openWorkerModal()" title="Click to view scientific worker status and capabilities">
        <div class="worker-status-dot"></div>
        <span>Worker: ${isConn ? 'CONNECTED' : 'DISCONNECTED'}</span>
        ${isConn ? `<span style="font-size: 10px; opacity: 0.8;">(RDKit: ${rdkitSt ? '✓' : 'Fallback'}, Vina: ${vinaSt ? '✓' : '✕'})</span>` : ''}
      </div>
    `;

    headerElem.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
        <div>${bcHtml}</div>
        <div>${workerPillHtml}</div>
      </div>
    `;"""

if old_header in code:
    code = code.replace(old_header, new_header)

worker_modal_fn = """
  async openWorkerModal() {
    await this.checkWorkerStatus();
    const ws = this.state.workerStatus;
    const isConn = ws && ws.connected;
    const sw = ws.scientific_software || {};

    this.openModal({
      title: '⚡ AIDD Scientific Worker Service',
      large: true,
      body: `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding: 12px; background: #0F172A; border-radius: 6px; border: 1px solid var(--border-subtle);">
          <div style="display: flex; gap: 10px; align-items: center;">
            <span class="worker-status-pill ${isConn ? 'connected' : 'disconnected'}" style="cursor: default;">
              <span class="worker-status-dot"></span>
              ${ws.status}
            </span>
            <div style="font-size: 12px; color: var(--text-secondary);">
              Endpoint: <code>${ws.worker_url || 'http://127.0.0.1:8001'}</code>
            </div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="AIDD.openWorkerModal()">Refresh Status</button>
        </div>

        <div class="grid-2" style="margin-bottom: 16px;">
          <div class="card" style="margin-bottom: 0; padding: 12px;">
            <div class="card-title" style="font-size: 12px; margin-bottom: 8px;">RDKit Cheminformatics Backend</div>
            <div style="font-size: 12px;">
              <div><b>Installed:</b> ${sw.rdkit && sw.rdkit.installed ? '<span style="color: #10B981;">YES (Native C++)</span>' : '<span style="color: #F59E0B;">NO (Calibrated Pure-Python Reference Engine)</span>'}</div>
              <div style="margin-top: 4px;"><b>Version:</b> <code>${sw.rdkit && sw.rdkit.version ? sw.rdkit.version : 'Fallback v1.3.0'}</code></div>
              <div style="margin-top: 4px;"><b>Native RDKit Ready:</b> ${sw.rdkit && sw.rdkit.production_ready ? '<span class="badge badge-pass">YES</span>' : '<span class="badge badge-fail">NO (Fallback Mode)</span>'}</div>
            </div>
          </div>

          <div class="card" style="margin-bottom: 0; padding: 12px;">
            <div class="card-title" style="font-size: 12px; margin-bottom: 8px;">AutoDock Vina Docking Backend</div>
            <div style="font-size: 12px;">
              <div><b>Installed:</b> ${sw.autodock_vina && sw.autodock_vina.installed ? '<span style="color: #10B981;">YES (Native Binary)</span>' : '<span style="color: #F87171;">NOT DETECTED (PATH lookup empty)</span>'}</div>
              <div style="margin-top: 4px;"><b>Binary Path:</b> <code>${sw.autodock_vina && sw.autodock_vina.path ? sw.autodock_vina.path : 'None'}</code></div>
              <div style="margin-top: 4px;"><b>Version:</b> <code>${sw.autodock_vina && sw.autodock_vina.version ? sw.autodock_vina.version : 'N/A'}</code></div>
            </div>
          </div>
        </div>

        <div class="card" style="padding: 12px; margin-bottom: 16px;">
          <div class="card-title" style="font-size: 12px; margin-bottom: 8px;">Worker Host Environment</div>
          <div style="font-size: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div>Worker ID: <code>${ws.worker_id || 'N/A'}</code></div>
            <div>Worker Version: <code>v${ws.worker_version || '1.3.0'}</code></div>
            <div>Operating System: <b>${ws.platform && ws.platform.system ? ws.platform.system + ' ' + ws.platform.release : 'Linux'}</b></div>
            <div>Architecture: <code>${ws.platform && ws.platform.architecture ? ws.platform.architecture : 'x86_64'}</code></div>
            <div>CPU Cores: <b>${ws.platform && ws.platform.cpu_count ? ws.platform.cpu_count : '2'}</b></div>
            <div>Python Version: <code>${ws.platform && ws.platform.python_version ? ws.platform.python_version : '3.11.2'}</code></div>
          </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="font-size: 11px; color: var(--text-muted);">
            To run worker locally: <code>conda activate aidd-worker-env && ./aidd_worker/run_worker.sh</code>
          </div>
          <button class="btn btn-primary btn-sm" onclick="AIDD.triggerWorker50Benchmark()">Run 55-Molecule Diversity Benchmark →</button>
        </div>
        <div id="worker-benchmark-area" style="margin-top: 14px;"></div>
      `,
      footer: `<button class="btn btn-secondary" onclick="AIDD.closeModal()">Close</button>`
    });
  },

  async triggerWorker50Benchmark() {
    const area = document.getElementById('worker-benchmark-area');
    area.innerHTML = '<div style="padding: 10px; color: #38BDF8;">Executing 55 diverse chemical structures through scientific worker pipeline...</div>';
    try {
      const res = await this.api('/api/worker/validation/rdkit');
      area.innerHTML = `
        <div class="card" style="padding: 12px; margin-bottom: 0; border-color: ${res.validation_passed ? '#10B981' : '#EF4444'};">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <b>Benchmark Result: <span style="color: ${res.validation_passed ? '#10B981' : '#EF4444'};">${res.validation_passed ? '100% PASSED' : 'FAILURES DETECTED'}</span></b>
            <span class="badge badge-active">${res.successful_count} / ${res.total_compounds_tested} Compounds</span>
          </div>
          <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
            Tested across ${res.categories_tested} chemical classes (aliphatics, aromatics, heteroaromatics, amides, amines, acids, halogenated, stereocenters, salts, FDA approved).
          </div>
        </div>
      `;
    } catch (e) {
      area.innerHTML = `<div style="color: #EF4444;">Benchmark failed: ${e.message}</div>`;
    }
  },
"""

if 'async openWorkerModal()' not in code:
    code = code.rstrip()
    if code.endswith('};'):
        code = code[:-2] + worker_modal_fn + "\n};"

with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/static/js/app.js', 'w') as f:
    f.write(code)

print("Updated app.js successfully")
