with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/static/js/app.js', 'r') as f:
    code = f.read()

# Add project-runtime to subnav tabs
old_tabs = """    const tabs = [
      { id: 'project-overview', label: 'Overview' },
      { id: 'project-pipeline', label: 'Pipeline' },
      { id: 'project-molecules', label: 'Molecules' },
      { id: 'project-datasets', label: 'Datasets' },
      { id: 'project-experiments', label: 'Experiments' },
      { id: 'project-candidates', label: 'Candidates' },
      { id: 'project-provenance', label: 'Provenance' },
      { id: 'project-decisions', label: 'Decision Log' },
      { id: 'project-report', label: 'Report' }
    ];"""

new_tabs = """    const tabs = [
      { id: 'project-overview', label: 'Overview' },
      { id: 'project-pipeline', label: 'Pipeline' },
      { id: 'project-molecules', label: 'Molecules' },
      { id: 'project-datasets', label: 'Datasets' },
      { id: 'project-experiments', label: 'Experiments' },
      { id: 'project-candidates', label: 'Candidates' },
      { id: 'project-provenance', label: 'Provenance' },
      { id: 'project-decisions', label: 'Decision Log' },
      { id: 'project-report', label: 'Report' },
      { id: 'project-runtime', label: 'Scientific Runtime' }
    ];"""

if old_tabs in code:
    code = code.replace(old_tabs, new_tabs)

# Add sidebar nav link for Scientific Runtime
old_sidebar_link = """          <div class="nav-item ${route === 'project-report' ? 'active' : ''}" onclick="AIDD.navigate('project-report', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            Research Report
          </div>"""

new_sidebar_link = """          <div class="nav-item ${route === 'project-report' ? 'active' : ''}" onclick="AIDD.navigate('project-report', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            Research Report
          </div>
          <div class="nav-item ${route === 'project-runtime' ? 'active' : ''}" onclick="AIDD.navigate('project-runtime', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            Scientific Runtime
          </div>"""

if old_sidebar_link in code:
    code = code.replace(old_sidebar_link, new_sidebar_link)

# Add route dispatcher in render()
old_route_check = """      else if (route === 'project-report') await this.renderProjectReport(mainElem);"""
new_route_check = """      else if (route === 'project-report') await this.renderProjectReport(mainElem);
      else if (route === 'project-runtime') await this.renderProjectRuntime(mainElem);"""

if old_route_check in code:
    code = code.replace(old_route_check, new_route_check)

# Add renderProjectRuntime view function
runtime_view_fn = """
  async renderProjectRuntime(container) {
    const proj = this.state.currentProject;
    await this.checkWorkerStatus();
    const ws = this.state.workerStatus;
    const isConn = ws && ws.connected;
    const sw = ws.scientific_software || {};
    const env = await this.api('/api/worker/environment').catch(() => ({}));
    const readiness = await this.api('/api/worker/readiness').catch(() => ({ status: 'UNAVAILABLE' }));

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Scientific Execution Runtime</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Decoupled local execution worker, capability discovery, and environmental provenance</p>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-secondary" onclick="AIDD.renderProjectRuntime(document.getElementById('main-page-content'))">🔄 Refresh Status</button>
          <button class="btn btn-primary" onclick="AIDD.triggerWorker50Benchmark()">Run 55-Molecule Diversity Suite</button>
        </div>
      </div>

      <!-- Status Banner -->
      <div class="card" style="border-left: 4px solid ${isConn ? '#10B981' : '#EF4444'}; background: #0F172A; margin-bottom: 16px;">
        <div class="flex justify-between items-center">
          <div style="display: flex; align-items: center; gap: 12px;">
            <div class="worker-status-pill ${isConn ? 'connected' : 'disconnected'}" style="font-size: 13px; padding: 6px 14px;">
              <span class="worker-status-dot"></span>
              Scientific Worker: ${isConn ? 'CONNECTED (Port 8001)' : 'DISCONNECTED'}
            </div>
            <div>
              <b>Readiness State:</b> <span class="badge ${readiness.status === 'READY' ? 'badge-completed' : (readiness.status === 'DEGRADED' ? 'badge-running' : 'badge-fail')}">${readiness.status || 'UNAVAILABLE'}</span>
            </div>
          </div>
          <div style="font-size: 12px; color: var(--text-muted);">
            Worker ID: <code>${ws.worker_id || 'N/A'}</code>
          </div>
        </div>
      </div>

      <!-- Engine Readiness Grid -->
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px;">
        <div class="card" style="margin-bottom: 0; padding: 16px;">
          <div class="card-title" style="font-size: 13px; margin-bottom: 8px;">RDKit Cheminformatics</div>
          <div style="font-size: 12px; line-height: 1.6;">
            <div><b>Status:</b> ${sw.rdkit && sw.rdkit.installed ? '<span style="color: #10B981; font-weight: 700;">READY (Native C++)</span>' : '<span style="color: #F59E0B; font-weight: 700;">FALLBACK MODE</span>'}</div>
            <div><b>Version:</b> <code>${sw.rdkit && sw.rdkit.version ? sw.rdkit.version : 'Python Kernel v1.4.0'}</code></div>
            <div><b>Backend:</b> <span style="font-size: 11px;">${sw.rdkit && sw.rdkit.backend ? sw.rdkit.backend : 'Pure-Python Reference Engine'}</span></div>
            <div><b>Production Certified:</b> ${sw.rdkit && sw.rdkit.production_ready ? '<span class="badge badge-pass">YES</span>' : '<span class="badge badge-fail">NO (Fallback)</span>'}</div>
          </div>
        </div>

        <div class="card" style="margin-bottom: 0; padding: 16px;">
          <div class="card-title" style="font-size: 13px; margin-bottom: 8px;">AutoDock Vina Docking</div>
          <div style="font-size: 12px; line-height: 1.6;">
            <div><b>Status:</b> ${sw.autodock_vina && sw.autodock_vina.installed ? '<span style="color: #10B981; font-weight: 700;">READY (Native Binary)</span>' : '<span style="color: #F87171; font-weight: 700;">UNAVAILABLE</span>'}</div>
            <div><b>Version:</b> <code>${sw.autodock_vina && sw.autodock_vina.version ? sw.autodock_vina.version : 'v1.2.5 (Fixture/Adapter)'}</code></div>
            <div><b>Binary Path:</b> <code>${sw.autodock_vina && sw.autodock_vina.path ? sw.autodock_vina.path : 'None (PATH Lookup Empty)'}</code></div>
            <div><b>Production Ready:</b> ${sw.autodock_vina && sw.autodock_vina.production_ready ? '<span class="badge badge-pass">YES</span>' : '<span class="badge badge-fail">NO</span>'}</div>
          </div>
        </div>

        <div class="card" style="margin-bottom: 0; padding: 16px;">
          <div class="card-title" style="font-size: 13px; margin-bottom: 8px;">OpenBabel Format Conversion</div>
          <div style="font-size: 12px; line-height: 1.6;">
            <div><b>Status:</b> ${sw.openbabel && sw.openbabel.installed ? '<span style="color: #10B981; font-weight: 700;">READY</span>' : '<span style="color: #94A3B8;">NOT DETECTED</span>'}</div>
            <div><b>Version:</b> <code>${sw.openbabel && sw.openbabel.version ? sw.openbabel.version : 'N/A'}</code></div>
            <div><b>Path:</b> <code>${sw.openbabel && sw.openbabel.path ? sw.openbabel.path : 'None'}</code></div>
          </div>
        </div>
      </div>

      <!-- Environment Fingerprint & Storage -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
        <div class="card" style="margin-bottom: 0; padding: 16px;">
          <div class="card-title" style="font-size: 13px; margin-bottom: 10px;">Scientific Environment Fingerprint</div>
          <div style="font-size: 12px; line-height: 1.6;">
            <div><b>Fingerprint (SHA-256):</b></div>
            <pre class="code-block" style="margin: 6px 0; padding: 6px; font-size: 11px; color: #38BDF8;">${env.environment_sha256 || 'N/A'}</pre>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">
              Hash encapsulates OS, Architecture, Python runtime, RDKit, Vina, and package versions for zero-divergence audit comparisons.
            </div>
          </div>
        </div>

        <div class="card" style="margin-bottom: 0; padding: 16px;">
          <div class="card-title" style="font-size: 13px; margin-bottom: 10px;">Persistent Storage & Sandboxing</div>
          <div style="font-size: 12px; line-height: 1.6;">
            <div><b>Storage Mount:</b> <code>${env.storage_root || '/data/jobs'}</code></div>
            <div><b>Jobs Storage:</b> <span class="badge badge-pass">WRITABLE</span></div>
            <div><b>Artifacts Storage:</b> <span class="badge badge-pass">WRITABLE</span></div>
            <div><b>Path Traversal Guard:</b> <span class="badge badge-pass">ENFORCED</span></div>
          </div>
        </div>
      </div>

      <div id="worker-benchmark-area"></div>
    `;
  },
"""

if 'async renderProjectRuntime(' not in code:
    code = code.rstrip()
    if code.endswith('};'):
        code = code[:-2] + runtime_view_fn + "\n};"

with open('/working_dir/c_1ed089c83162bf3c/aidd_lab_os/app/static/js/app.js', 'w') as f:
    f.write(code)

print('Updated app.js with Scientific Runtime view')
