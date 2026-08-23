/**
 * AIDD Lab OS - Production Scientific Workspace Client
 * Core State Management, Router, and UI Controller
 */

const AIDD = {
  state: {
    currentRoute: 'dashboard',
    currentProjectId: null,
    projects: [],
    currentProject: null,
    engineStatus: null,
    workerStatus: null,
    moleculesData: { total: 0, molecules: [] },
    datasets: [],
    experiments: [],
    candidates: [],
    decisions: [],
    provenance: { nodes: [], edges: [] },
    filters: {
      search: '',
      lipinski_only: false,
      min_mw: null,
      max_mw: null,
      min_logp: null,
      max_logp: null,
      max_docking: null,
      tier: 'All',
      sort_by: 'created_at',
      sort_order: 'desc',
      limit: 100,
      offset: 0
    }
  },

  async init() {
    this.bindGlobalEvents();
    await this.loadEngineStatus();
    await this.checkWorkerStatus();
    await this.loadProjects();
    this.handleRouteFromUrl();
  },

  
  async checkWorkerStatus() {
    try {
      this.state.workerStatus = await this.api('/api/worker/status');
    } catch (e) {
      this.state.workerStatus = { connected: false, status: 'DISCONNECTED' };
    }
  },

  async loadEngineStatus() {
    try {
      this.state.engineStatus = await this.api('/api/scientific/status');
    } catch (e) {
      console.warn('Could not fetch scientific status', e);
    }
  },

  // -----------------------------------------------------------------
  // API HELPERS
  // -----------------------------------------------------------------
  async api(endpoint, options = {}) {
    try {
      const res = await fetch(endpoint, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'API request failed');
      }
      return await res.json();
    } catch (e) {
      console.error('API Error:', e);
      this.showToast(e.message, 'error');
      throw e;
    }
  },

  showToast(msg, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `aidd-toast aidd-toast-${type}`;
    toast.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 9999;
      background: ${type === 'error' ? '#7F1D1D' : (type === 'success' ? '#064E3B' : '#1E293B')};
      color: #FFF; border: 1px solid ${type === 'error' ? '#EF4444' : (type === 'success' ? '#10B981' : '#38BDF8')};
      padding: 10px 16px; border-radius: 6px; font-size: 12px; font-weight: 500;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5); display: flex; align-items: center; gap: 8px;
    `;
    toast.innerHTML = `<span>${msg}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 3500);
  },

  getOriginBadge(origin) {
    const org = (origin || 'COMPUTED').toUpperCase();
    let cls = 'badge-origin-computed';
    if (org === 'IMPORTED') cls = 'badge-origin-imported';
    else if (org === 'SIMULATED') cls = 'badge-origin-simulated';
    else if (org === 'DEMO') cls = 'badge-origin-demo';
    else if (org === 'MANUAL') cls = 'badge-origin-manual';
    return `<span class="badge ${cls}" title="Scientific Data Origin">${org}</span>`;
  },

  // -----------------------------------------------------------------
  // ROUTING & NAVIGATION
  // -----------------------------------------------------------------
  navigate(route, projectId = null, updateHistory = true) {
    this.state.currentRoute = route;
    if (projectId !== undefined && projectId !== null) {
      this.state.currentProjectId = projectId;
    }

    if (updateHistory) {
      let path = '/dashboard';
      if (route === 'projects') path = '/projects';
      else if (this.state.currentProjectId) {
        const sub = route.replace('project-', '');
        path = sub === 'overview' ? `/projects/${this.state.currentProjectId}` : `/projects/${this.state.currentProjectId}/${sub}`;
      }
      window.history.pushState({ route, projectId: this.state.currentProjectId }, '', path);
    }

    this.render();
  },

  handleRouteFromUrl() {
    const path = window.location.pathname;
    if (path === '/' || path === '/dashboard') {
      this.navigate('dashboard', null, false);
    } else if (path === '/projects') {
      this.navigate('projects', null, false);
    } else if (path.startsWith('/projects/')) {
      const parts = path.split('/').filter(Boolean);
      const projId = parts[1];
      const sub = parts[2] || 'overview';
      this.navigate(`project-${sub}`, projId, false);
    } else {
      this.navigate('dashboard', null, false);
    }
  },

  bindGlobalEvents() {
    window.addEventListener('popstate', (e) => {
      if (e.state) {
        this.navigate(e.state.route, e.state.projectId, false);
      } else {
        this.handleRouteFromUrl();
      }
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeModal();
    });
  },

  async loadProjects() {
    this.state.projects = await this.api('/api/projects');
    if (!this.state.currentProjectId && this.state.projects.length > 0) {
      this.state.currentProjectId = this.state.projects[0].id;
    }
  },

  async loadProjectContext(projectId) {
    if (!projectId) return;
    this.state.currentProject = await this.api(`/api/projects/${projectId}`);
  },

  // -----------------------------------------------------------------
  // MAIN RENDER DISPATCHER
  // -----------------------------------------------------------------
  async render() {
    const route = this.state.currentRoute;
    const projId = this.state.currentProjectId;

    this.renderSidebar();
    this.renderHeader();

    const mainElem = document.getElementById('main-page-content');
    const subnavElem = document.getElementById('project-subnav-bar');

    if (route.startsWith('project-') && projId) {
      subnavElem.style.display = 'flex';
      this.renderProjectSubnav(route);
      await this.loadProjectContext(projId);

      if (route === 'project-overview') await this.renderProjectOverview(mainElem);
      else if (route === 'project-pipeline') await this.renderProjectPipeline(mainElem);
      else if (route === 'project-molecules') await this.renderProjectMolecules(mainElem);
      else if (route === 'project-datasets') await this.renderProjectDatasets(mainElem);
      else if (route === 'project-experiments') await this.renderProjectExperiments(mainElem);
      else if (route === 'project-candidates') await this.renderProjectCandidates(mainElem);
      else if (route === 'project-provenance') await this.renderProjectProvenance(mainElem);
      else if (route === 'project-decisions') await this.renderProjectDecisions(mainElem);
      else if (route === 'project-report') await this.renderProjectReport(mainElem);
      else if (route === 'project-runtime') await this.renderProjectRuntime(mainElem);
    } else {
      subnavElem.style.display = 'none';
      if (route === 'dashboard') await this.renderGlobalDashboard(mainElem);
      else if (route === 'projects') await this.renderProjectsList(mainElem);
    }
  },

  // -----------------------------------------------------------------
  // SIDEBAR & HEADER
  // -----------------------------------------------------------------
  renderSidebar() {
    const route = this.state.currentRoute;
    const projId = this.state.currentProjectId;
    const currProj = this.state.projects.find(p => p.id === projId) || this.state.projects[0];
    const eng = this.state.engineStatus;

    const sidebarElem = document.getElementById('app-sidebar');
    if (!sidebarElem) return;

    sidebarElem.innerHTML = `
      <div class="sidebar-header">
        <div class="brand-icon">AIDD</div>
        <div>
          <div class="brand-title">AIDD Lab OS</div>
          <div class="brand-tagline">Scientific Provenance</div>
        </div>
      </div>

      <div class="sidebar-project-selector">
        <div class="form-label" style="margin-bottom: 4px;">Active Workspace</div>
        <button class="project-select-btn" onclick="AIDD.openProjectSwitchModal()">
          <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            ${currProj ? currProj.name : 'Select Project'}
          </span>
          <span style="color: var(--accent-cyan);">▾</span>
        </button>
      </div>

      <div class="sidebar-nav">
        <div class="nav-section-title">Global</div>
        <div class="nav-item ${route === 'dashboard' ? 'active' : ''}" onclick="AIDD.navigate('dashboard')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          Dashboard
        </div>
        <div class="nav-item ${route === 'projects' ? 'active' : ''}" onclick="AIDD.navigate('projects')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          Projects
          <span class="nav-badge">${this.state.projects.length}</span>
        </div>

        ${projId ? `
          <div class="nav-section-title" style="margin-top: 12px;">Active Project</div>
          <div class="nav-item ${route === 'project-overview' ? 'active' : ''}" onclick="AIDD.navigate('project-overview', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            Overview
          </div>
          <div class="nav-item ${route === 'project-pipeline' ? 'active' : ''}" onclick="AIDD.navigate('project-pipeline', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            Pipeline
          </div>
          <div class="nav-item ${route === 'project-molecules' ? 'active' : ''}" onclick="AIDD.navigate('project-molecules', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 9v3a3 3 0 0 0 3 3h6"/></svg>
            Molecule Library
          </div>
          <div class="nav-item ${route === 'project-datasets' ? 'active' : ''}" onclick="AIDD.navigate('project-datasets', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            Datasets
          </div>
          <div class="nav-item ${route === 'project-experiments' ? 'active' : ''}" onclick="AIDD.navigate('project-experiments', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Experiments
          </div>
          <div class="nav-item ${route === 'project-candidates' ? 'active' : ''}" onclick="AIDD.navigate('project-candidates', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            Candidate Selection
          </div>
          <div class="nav-item ${route === 'project-provenance' ? 'active' : ''}" onclick="AIDD.navigate('project-provenance', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
            Provenance DAG
          </div>
          <div class="nav-item ${route === 'project-decisions' ? 'active' : ''}" onclick="AIDD.navigate('project-decisions', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            Decision Log
          </div>
          <div class="nav-item ${route === 'project-report' ? 'active' : ''}" onclick="AIDD.navigate('project-report', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            Research Report
          </div>
          <div class="nav-item ${route === 'project-runtime' ? 'active' : ''}" onclick="AIDD.navigate('project-runtime', '${projId}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            Scientific Runtime
          </div>
        ` : ''}
      </div>

      <div class="sidebar-footer">
        <div style="font-size: 10px; color: var(--text-muted);">
          <div>Engine: <span style="color: var(--accent-cyan); font-weight: 600;">${eng ? (eng.has_rdkit ? 'RDKit Native' : 'Calibrated Fallback') : 'Initializing...'}</span></div>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="AIDD.openAuditModal()" title="Run Scientific Regression Audit">Audit</button>
      </div>
    `;
  },

  renderHeader() {
    const route = this.state.currentRoute;
    const proj = this.state.currentProject;
    const headerElem = document.getElementById('app-header-breadcrumbs');
    if (!headerElem) return;

    let bcHtml = `<span class="breadcrumb-item" onclick="AIDD.navigate('dashboard')">Home</span>`;

    if (route === 'dashboard') {
      bcHtml += ` <span class="breadcrumb-sep">/</span> <span class="breadcrumb-current">Dashboard</span>`;
    } else if (route === 'projects') {
      bcHtml += ` <span class="breadcrumb-sep">/</span> <span class="breadcrumb-current">Projects</span>`;
    } else if (proj) {
      bcHtml += ` <span class="breadcrumb-sep">/</span> <span class="breadcrumb-item" onclick="AIDD.navigate('project-overview', '${proj.id}')">${proj.name}</span>`;
      const subName = route.replace('project-', '').replace(/^\w/, c => c.toUpperCase());
      bcHtml += ` <span class="breadcrumb-sep">/</span> <span class="breadcrumb-current">${subName}</span>`;
    }

    const ws = this.state.workerStatus;
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
    `;
  },

  renderProjectSubnav(currentRoute) {
    const projId = this.state.currentProjectId;
    const subnavElem = document.getElementById('project-subnav-bar');
    if (!subnavElem) return;

    const tabs = [
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
    ];

    subnavElem.innerHTML = tabs.map(t => `
      <div class="subnav-tab ${currentRoute === t.id ? 'active' : ''}" onclick="AIDD.navigate('${t.id}', '${projId}')">
        ${t.label}
      </div>
    `).join('');
  },

  // -----------------------------------------------------------------
  // VIEW: GLOBAL DASHBOARD
  // -----------------------------------------------------------------
  async renderGlobalDashboard(container) {
    const projects = await this.api('/api/projects');
    const totalMols = projects.reduce((acc, p) => acc + (p.molecule_count || 0), 0);
    const totalExps = projects.reduce((acc, p) => acc + (p.experiment_count || 0), 0);
    const totalCands = projects.reduce((acc, p) => acc + (p.candidate_count || 0), 0);
    const failedExps = projects.reduce((acc, p) => acc + (p.failed_experiments || 0), 0);

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Research Workspace Dashboard</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">AIDD Lab OS — Provenance-Tracking & Validated Computational Drug Discovery</p>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-secondary" onclick="AIDD.openAuditModal()">🔬 Scientific Regression Audit</button>
          <button class="btn btn-secondary" onclick="AIDD.resetDemoData()">Reset EGFR Demo</button>
          <button class="btn btn-primary" onclick="AIDD.openNewProjectModal()">+ Create Project</button>
        </div>
      </div>

      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Active Research Projects</div>
          <div class="metric-value">${projects.length}</div>
          <div class="metric-subtext">Structure & Ligand Campaigns</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Validated Compounds</div>
          <div class="metric-value">${totalMols}</div>
          <div class="metric-subtext">Standardized with SHA-256</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Immutable Experiments</div>
          <div class="metric-value">${totalExps}</div>
          <div class="metric-subtext">Manifests & Environment captured</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Priority Lead Candidates</div>
          <div class="metric-value" style="color: #A78BFA;">${totalCands}</div>
          <div class="metric-subtext">Transparent weighted ranking</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Failures Audited</div>
          <div class="metric-value" style="color: ${failedExps > 0 ? '#EF4444' : '#10B981'};">${failedExps}</div>
          <div class="metric-subtext">Documented exclusion logs</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">Research Projects</div>
          <button class="btn btn-secondary btn-sm" onclick="AIDD.openNewProjectModal()">New Project</button>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>Project Name</th>
                <th>Target Protein</th>
                <th>Disease Indication</th>
                <th>Current Stage</th>
                <th>Molecules</th>
                <th>Experiments</th>
                <th>Leads</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${projects.map(p => `
                <tr class="clickable" onclick="AIDD.navigate('project-overview', '${p.id}')">
                  <td><b>${p.name}</b></td>
                  <td><code>${p.target_protein || 'Unspecified'}</code></td>
                  <td>${p.disease_indication || 'N/A'}</td>
                  <td><span class="badge badge-active">${p.current_stage || 'Dataset'}</span></td>
                  <td><b>${p.molecule_count || 0}</b></td>
                  <td>${p.experiment_count || 0}</td>
                  <td><span class="badge badge-lead">${p.candidate_count || 0} Leads</span></td>
                  <td>
                    <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); AIDD.navigate('project-overview', '${p.id}')">Open Workspace →</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  // -----------------------------------------------------------------
  // VIEW: PROJECTS LIST
  // -----------------------------------------------------------------
  async renderProjectsList(container) {
    const projects = await this.api('/api/projects');
    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Research Projects</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Manage all computational drug discovery campaigns</p>
        </div>
        <button class="btn btn-primary" onclick="AIDD.openNewProjectModal()">+ New Project</button>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px;">
        ${projects.map(p => `
          <div class="card" style="margin-bottom: 0; cursor: pointer;" onclick="AIDD.navigate('project-overview', '${p.id}')">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
              <h3 style="font-size: 15px; font-weight: 700; color: #F8FAFC;">${p.name}</h3>
              <span class="badge badge-active">${p.current_stage}</span>
            </div>
            <div style="margin-top: 8px; font-size: 12px; color: var(--text-secondary); min-height: 36px;">
              ${p.description || 'No description provided.'}
            </div>
            <div style="margin-top: 12px; padding: 10px; background: #070A12; border-radius: 6px; font-size: 11.5px;">
              <div><b>Target:</b> <code>${p.target_protein || 'N/A'}</code></div>
              <div style="margin-top: 4px;"><b>Indication:</b> ${p.disease_indication || 'N/A'}</div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--border-subtle); font-size: 12px;">
              <span><b>${p.molecule_count || 0}</b> molecules • <b>${p.experiment_count || 0}</b> exps</span>
              <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); AIDD.navigate('project-overview', '${p.id}')">Open →</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  },

  // -----------------------------------------------------------------
  // VIEW: PROJECT OVERVIEW
  // -----------------------------------------------------------------
  async renderProjectOverview(container) {
    const proj = this.state.currentProject;
    if (!proj) return;

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <h1 style="font-size: 22px; font-weight: 700;">${proj.name}</h1>
            <span class="badge badge-active">${proj.current_stage}</span>
          </div>
          <p style="color: var(--text-secondary); font-size: 13px; margin-top: 4px;">${proj.description || ''}</p>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-secondary" onclick="window.open('/api/projects/${proj.id}/reproducibility-bundle')">📦 Export Reproducibility Bundle (.ZIP)</button>
          <button class="btn btn-secondary" onclick="AIDD.openImportModal('${proj.id}')">Import Molecules</button>
          <button class="btn btn-primary" onclick="AIDD.openNewExperimentModal('${proj.id}')">+ New Experiment</button>
        </div>
      </div>

      <!-- Hypothesis Card -->
      <div class="card" style="border-left: 4px solid var(--accent-cyan); background: #0F172A;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div>
            <div class="form-label" style="color: var(--accent-cyan);">Project Hypothesis & Objective</div>
            <p style="font-size: 13px; color: #E2E8F0; margin-top: 4px; font-style: italic;">
              "${proj.hypothesis || 'No scientific hypothesis defined yet.'}"
            </p>
          </div>
          <div style="text-align: right; font-size: 12px; color: var(--text-muted); min-width: 220px;">
            <div>Target: <code>${proj.target_protein || 'N/A'}</code></div>
            <div>Indication: <b>${proj.disease_indication || 'N/A'}</b></div>
          </div>
        </div>
      </div>

      <!-- Pipeline Track -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">Discovery Pipeline Progress</div>
          <button class="btn btn-secondary btn-sm" onclick="AIDD.navigate('project-pipeline', '${proj.id}')">Interactive Pipeline →</button>
        </div>
        <div class="pipeline-track">
          <div class="pipeline-step ${proj.molecule_count > 0 ? 'completed' : 'active'}">
            <div class="pipeline-step-num">Stage 01</div>
            <div class="pipeline-step-title">Dataset Ingestion</div>
            <div class="pipeline-step-desc">${proj.molecule_count} compounds parsed</div>
          </div>
          <div class="pipeline-step ${proj.current_stage !== 'Dataset' ? 'completed' : ''}">
            <div class="pipeline-step-num">Stage 02</div>
            <div class="pipeline-step-title">Standardization</div>
            <div class="pipeline-step-desc">Desalted & Ro5 Filter</div>
          </div>
          <div class="pipeline-step ${['Docking', 'ADMET', 'Candidate Selection'].includes(proj.current_stage) ? 'completed' : ''}">
            <div class="pipeline-step-num">Stage 03</div>
            <div class="pipeline-step-title">Docking Screen</div>
            <div class="pipeline-step-desc">Binding free energies</div>
          </div>
          <div class="pipeline-step ${['ADMET', 'Candidate Selection'].includes(proj.current_stage) ? 'completed' : ''}">
            <div class="pipeline-step-num">Stage 04</div>
            <div class="pipeline-step-title">ADMET Profiling</div>
            <div class="pipeline-step-desc">Pharmacokinetics & Safety</div>
          </div>
          <div class="pipeline-step ${proj.current_stage === 'Candidate Selection' ? 'completed' : ''}">
            <div class="pipeline-step-num">Stage 05</div>
            <div class="pipeline-step-title">Candidate Selection</div>
            <div class="pipeline-step-desc">${proj.candidate_count} Priority Leads</div>
          </div>
        </div>
      </div>

      <!-- Metrics -->
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Screened Compounds</div>
          <div class="metric-value">${proj.molecule_count}</div>
          <div class="metric-subtext">Across ${proj.dataset_count} dataset versions</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Completed Experiments</div>
          <div class="metric-value">${proj.completed_experiments}</div>
          <div class="metric-subtext">${proj.experiment_count} total runs</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Priority Leads</div>
          <div class="metric-value" style="color: #A78BFA;">${proj.candidate_count}</div>
          <div class="metric-subtext">Composite rank >= 78%</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Logged Decisions</div>
          <div class="metric-value">${proj.decision_count}</div>
          <div class="metric-subtext">Audit trail entries</div>
        </div>
      </div>

      <!-- Top Candidates & Recent Experiments -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <div class="card">
          <div class="card-header">
            <div class="card-title">Top Drug Candidates</div>
            <button class="btn btn-secondary btn-sm" onclick="AIDD.navigate('project-candidates', '${proj.id}')">View All →</button>
          </div>
          ${proj.top_candidates && proj.top_candidates.length > 0 ? `
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Candidate</th>
                    <th>Score</th>
                    <th>Origin</th>
                    <th>Tier</th>
                  </tr>
                </thead>
                <tbody>
                  ${proj.top_candidates.map(c => `
                    <tr class="clickable" onclick="AIDD.openMoleculeModal('${c.molecule_id}')">
                      <td><b>#${c.rank_position}</b></td>
                      <td><b>${c.molecule_name}</b><br><code style="font-size: 10px;">${c.molecule_id}</code></td>
                      <td><b>${c.composite_score.toFixed(1)}</b></td>
                      <td>${AIDD.getOriginBadge(c.docking_origin || 'COMPUTED')}</td>
                      <td><span class="badge ${c.tier === 'Lead Candidate' ? 'badge-lead' : 'badge-backup'}">${c.tier}</span></td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : '<p class="text-muted" style="padding: 16px;">No candidates ranked yet.</p>'}
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">Recent Experiment Runs</div>
            <button class="btn btn-secondary btn-sm" onclick="AIDD.navigate('project-experiments', '${proj.id}')">All Runs →</button>
          </div>
          ${proj.recent_experiments && proj.recent_experiments.length > 0 ? `
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Experiment</th>
                    <th>Tool</th>
                    <th>Status</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  ${proj.recent_experiments.map(e => `
                    <tr class="clickable" onclick="AIDD.openExperimentModal('${e.id}')">
                      <td><b>${e.name}</b><br><span style="font-size: 10px; color: var(--text-muted);">${e.stage}</span></td>
                      <td><code>${e.tool}</code></td>
                      <td><span class="badge badge-${e.status}">${e.status}</span></td>
                      <td>${e.duration_seconds}s</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : '<p class="text-muted" style="padding: 16px;">No experiments run yet.</p>'}
        </div>
      </div>
    `;
  },

  // -----------------------------------------------------------------
  // VIEW: PIPELINE VISUALIZER
  // -----------------------------------------------------------------
  async renderProjectPipeline(container) {
    const proj = this.state.currentProject;
    const datasets = await this.api(`/api/projects/${proj.id}/datasets`);
    const latestDs = datasets.length > 0 ? datasets[datasets.length - 1] : null;

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Computational Pipeline Architecture</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Manage and trigger pipeline stages with automated dataset versioning & origin tagging</p>
        </div>
        <button class="btn btn-primary" onclick="AIDD.openNewExperimentModal('${proj.id}')">+ Run Custom Experiment</button>
      </div>

      <div style="display: flex; flex-direction: column; gap: 16px;">
        <!-- Stage 1: Dataset -->
        <div class="card" style="border-left: 4px solid #38BDF8;">
          <div class="flex items-center justify-between">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="badge badge-completed">Stage 01 • Ingestion</span>
                ${AIDD.getOriginBadge('COMPUTED')}
              </div>
              <h3 style="font-size: 16px; margin-top: 4px;">Raw Dataset Ingestion & Chemical Parsing</h3>
              <p style="color: var(--text-secondary); font-size: 12px;">SMILES sanitization, canonicalization, valence validation, and SHA-256 fingerprint generation.</p>
            </div>
            <button class="btn btn-secondary" onclick="AIDD.openImportModal('${proj.id}')">+ Import More SMILES</button>
          </div>
        </div>

        <!-- Stage 2: Standardization -->
        <div class="card" style="border-left: 4px solid #10B981;">
          <div class="flex items-center justify-between">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="badge badge-completed">Stage 02 • Preprocessing</span>
                ${AIDD.getOriginBadge('COMPUTED')}
              </div>
              <h3 style="font-size: 16px; margin-top: 4px;">Standardization, Desalting & Drug-Likeness (Ro5) Filter</h3>
              <p style="color: var(--text-secondary); font-size: 12px;">Strips inorganic counterions, neutralizes formal charges, and enforces Lipinski MW & LogP cutoffs.</p>
            </div>
            <button class="btn btn-primary" onclick="AIDD.openPreprocessModal('${proj.id}', '${latestDs ? latestDs.id : ''}')">Launch Standardization →</button>
          </div>
        </div>

        <!-- Stage 3: Docking -->
        <div class="card" style="border-left: 4px solid #F59E0B;">
          <div class="flex items-center justify-between">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="badge badge-running">Stage 03 • Docking</span>
                ${AIDD.getOriginBadge('IMPORTED')}
              </div>
              <h3 style="font-size: 16px; margin-top: 4px;">AutoDock Vina Structure-Based Screen / Import</h3>
              <p style="color: var(--text-secondary); font-size: 12px;">Binding free energies with full receptor hashes, grid coordinates (x,y,z), and exhaustiveness parameters.</p>
            </div>
            <button class="btn btn-primary" onclick="AIDD.openDockingModal('${proj.id}', '${latestDs ? latestDs.id : ''}')">Launch / Import Docking →</button>
          </div>
        </div>

        <!-- Stage 4: ADMET -->
        <div class="card" style="border-left: 4px solid #EC4899;">
          <div class="flex items-center justify-between">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="badge badge-running">Stage 04 • Pharmacokinetics</span>
                ${AIDD.getOriginBadge('IMPORTED')}
              </div>
              <h3 style="font-size: 16px; margin-top: 4px;">In Silico ADMET & Safety Profiling</h3>
              <p style="color: var(--text-secondary); font-size: 12px;">Evaluates BOILED-Egg GI absorption, BBB penetrance, CYP450 inhibition, and Ames/hERG toxicity flags.</p>
            </div>
            <button class="btn btn-primary" onclick="AIDD.openADMETModal('${proj.id}', '${latestDs ? latestDs.id : ''}')">Launch / Import ADMET →</button>
          </div>
        </div>

        <!-- Stage 5: Candidates -->
        <div class="card" style="border-left: 4px solid #8B5CF6;">
          <div class="flex items-center justify-between">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="badge badge-lead">Stage 05 • Candidate Selection</span>
                ${AIDD.getOriginBadge('COMPUTED')}
              </div>
              <h3 style="font-size: 16px; margin-top: 4px;">Mathematically Transparent Multi-Parameter Ranking</h3>
              <p style="color: var(--text-secondary); font-size: 12px;">Multi-objective composite optimization across Docking, QSAR, ADMET, and QED with customizable missing-data policies.</p>
            </div>
            <button class="btn btn-primary" onclick="AIDD.navigate('project-candidates', '${proj.id}')">Configure Weights & Rank →</button>
          </div>
        </div>
      </div>
    `;
  },

  // -----------------------------------------------------------------
  // VIEW: MOLECULE LIBRARY
  // -----------------------------------------------------------------
  async renderProjectMolecules(container) {
    const proj = this.state.currentProject;
    const f = this.state.filters;

    const queryParams = new URLSearchParams({
      search: f.search || '',
      lipinski_only: f.lipinski_only ? 'true' : 'false',
      sort_by: f.sort_by,
      sort_order: f.sort_order,
      tier: f.tier || 'All',
      limit: f.limit,
      offset: f.offset
    });
    if (f.min_mw) queryParams.set('min_mw', f.min_mw);
    if (f.max_mw) queryParams.set('max_mw', f.max_mw);
    if (f.max_docking) queryParams.set('max_docking', f.max_docking);

    const data = await this.api(`/api/projects/${proj.id}/molecules?${queryParams.toString()}`);
    this.state.moleculesData = data;

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Molecule Library</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">${data.total} parsed compounds with full 2D skeletal structures, fingerprints, and descriptors</p>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-secondary" onclick="AIDD.openImportModal('${proj.id}')">+ Import Molecules</button>
        </div>
      </div>

      <!-- Filters & Search Toolbar -->
      <div class="card" style="padding: 12px 16px; margin-bottom: 16px;">
        <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
          <input type="text" class="form-control" placeholder="Search by molecule ID, name, SMILES, formula..." style="width: 280px;" value="${f.search}" oninput="AIDD.onSearchMolecules(this.value)">
          
          <select class="form-control" style="width: 140px;" onchange="AIDD.onFilterTier(this.value)">
            <option value="All" ${f.tier === 'All' ? 'selected' : ''}>All Tiers</option>
            <option value="Lead Candidate" ${f.tier === 'Lead Candidate' ? 'selected' : ''}>Lead Candidate</option>
            <option value="Backup Lead" ${f.tier === 'Backup Lead' ? 'selected' : ''}>Backup Lead</option>
            <option value="Follow-up" ${f.tier === 'Follow-up' ? 'selected' : ''}>Follow-up</option>
          </select>

          <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer; user-select: none;">
            <input type="checkbox" ${f.lipinski_only ? 'checked' : ''} onchange="AIDD.onToggleLipinski(this.checked)">
            Ro5 Pass Only
          </label>

          <div style="display: flex; align-items: center; gap: 6px; margin-left: auto;">
            <span style="font-size: 11px; color: var(--text-muted);">Sort By:</span>
            <select class="form-control" style="width: 150px;" onchange="AIDD.onSortMolecules(this.value)">
              <option value="created_at" ${f.sort_by === 'created_at' ? 'selected' : ''}>Import Date</option>
              <option value="molecular_weight" ${f.sort_by === 'molecular_weight' ? 'selected' : ''}>Molecular Weight</option>
              <option value="logp" ${f.sort_by === 'logp' ? 'selected' : ''}>LogP</option>
              <option value="tpsa" ${f.sort_by === 'tpsa' ? 'selected' : ''}>TPSA</option>
              <option value="docking_score" ${f.sort_by === 'docking_score' ? 'selected' : ''}>Docking Score</option>
              <option value="candidate_score" ${f.sort_by === 'candidate_score' ? 'selected' : ''}>Candidate Score</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Molecule Table -->
      <div class="card" style="padding: 0; overflow: hidden;">
        <div class="table-container" style="border: none;">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 60px;">2D Structure</th>
                <th>Molecule ID</th>
                <th>Name</th>
                <th>Formula</th>
                <th>MW (Da)</th>
                <th>LogP</th>
                <th>TPSA (Å²)</th>
                <th>Ro5</th>
                <th>Docking</th>
                <th>ADMET</th>
                <th>Candidate Tier</th>
              </tr>
            </thead>
            <tbody>
              ${data.molecules.map(m => `
                <tr class="clickable" onclick="AIDD.openMoleculeModal('${m.id}')">
                  <td><div class="mol-thumb">${m.svg_structure || ''}</div></td>
                  <td><code>${m.id}</code></td>
                  <td><b>${m.name}</b></td>
                  <td><code>${m.formula || ''}</code></td>
                  <td>${m.molecular_weight ? m.molecular_weight.toFixed(1) : 'N/A'}</td>
                  <td>${m.logp ? m.logp.toFixed(2) : 'N/A'}</td>
                  <td>${m.tpsa ? m.tpsa.toFixed(1) : 'N/A'}</td>
                  <td>
                    <span class="badge ${m.lipinski_pass ? 'badge-pass' : 'badge-fail'}">
                      ${m.lipinski_pass ? 'PASS' : `FAIL (${m.lipinski_violations})`}
                    </span>
                  </td>
                  <td>
                    ${m.docking_score !== null && m.docking_score !== undefined ? `
                      <code>${m.docking_score.toFixed(1)} kcal/mol</code>
                      ${AIDD.getOriginBadge(m.docking_origin || 'IMPORTED')}
                    ` : '<span class="text-muted">Not Docked</span>'}
                  </td>
                  <td>
                    ${m.admet_risk_level ? `
                      <span class="badge ${m.admet_risk_level === 'Low Risk' ? 'badge-low-risk' : (m.admet_risk_level === 'Moderate Risk' ? 'badge-moderate-risk' : 'badge-high-risk')}">
                        ${m.admet_risk_level}
                      </span>
                    ` : '<span class="text-muted">—</span>'}
                  </td>
                  <td>
                    ${m.candidate_tier && m.candidate_tier !== 'Unassigned' ? `
                      <span class="badge ${m.candidate_tier === 'Lead Candidate' ? 'badge-lead' : 'badge-backup'}">
                        ${m.candidate_tier}
                      </span>
                    ` : '<span class="text-muted">—</span>'}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  onSearchMolecules(val) {
    this.state.filters.search = val;
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => { this.render(); }, 250);
  },

  onFilterTier(val) {
    this.state.filters.tier = val;
    this.render();
  },

  onToggleLipinski(checked) {
    this.state.filters.lipinski_only = checked;
    this.render();
  },

  onSortMolecules(val) {
    this.state.filters.sort_by = val;
    this.render();
  },

  // -----------------------------------------------------------------
  // VIEW: MOLECULE DETAIL MODAL
  // -----------------------------------------------------------------
  async openMoleculeModal(moleculeId) {
    const mol = await this.api(`/api/molecules/${moleculeId}`);
    if (!mol) return;

    let fpObj = {};
    try { fpObj = json.loads ? JSON.parse(mol.fingerprint_bits) : JSON.parse(mol.fingerprint_bits || '{}'); } catch(e){}

    const timelineHtml = (mol.timeline || []).map(item => `
      <div class="timeline-item">
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <div class="timeline-header">
            <div class="timeline-title">${item.title}</div>
            <div class="timeline-date">${item.timestamp ? item.timestamp.substring(0, 19).replace('T', ' ') : ''}</div>
          </div>
          <div class="timeline-details">${item.details}</div>
          <div style="margin-top: 6px; display: flex; align-items: center; gap: 8px; font-size: 11px;">
            <span class="badge badge-active">${item.tool}</span>
            ${AIDD.getOriginBadge(item.origin || 'COMPUTED')}
            ${item.experiment_id ? `<a href="#" style="color: var(--accent-cyan);" onclick="event.preventDefault(); AIDD.openExperimentModal('${item.experiment_id}')">Inspect Exp (${item.experiment_id}) →</a>` : ''}
          </div>
        </div>
      </div>
    `).join('');

    this.openModal({
      title: `${mol.name} (${mol.id})`,
      large: true,
      body: `
        <div style="display: grid; grid-template-columns: 280px 1fr; gap: 24px;">
          <!-- Left Column -->
          <div>
            <div style="width: 100%; height: 210px; background: #070A12; border: 1px solid var(--border-subtle); border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center;">
              ${mol.svg_structure || ''}
            </div>
            
            <div style="margin-top: 14px; padding: 12px; background: #0F172A; border-radius: 6px; border: 1px solid var(--border-subtle);">
              <div class="form-label" style="margin-bottom: 4px;">Original Ingested SMILES</div>
              <pre class="code-block" style="padding: 4px 6px; font-size: 10px; word-break: break-all; white-space: pre-wrap; max-height: 60px;">${mol.original_smiles || mol.smiles}</pre>

              ${mol.standardized_smiles && mol.standardized_smiles !== mol.original_smiles ? `
                <div class="form-label" style="margin-top: 8px; margin-bottom: 4px; color: var(--accent-green);">Standardized Canonical SMILES</div>
                <pre class="code-block" style="padding: 4px 6px; font-size: 10px; word-break: break-all; white-space: pre-wrap; max-height: 60px; color: #34D399;">${mol.standardized_smiles}</pre>
              ` : ''}

              <div style="margin-top: 8px; font-size: 10px; color: var(--text-muted);">
                SHA-256: <code>${(mol.sha256_hash || '').substring(0, 16)}...</code>
              </div>
            </div>

            <div style="margin-top: 14px;">
              <table style="width: 100%; font-size: 11.5px;">
                <tr><td class="text-secondary" style="padding: 3px 0;">Formula</td><td><b>${mol.formula}</b></td></tr>
                <tr><td class="text-secondary" style="padding: 3px 0;">Molecular Weight</td><td><b>${mol.molecular_weight} Da</b></td></tr>
                <tr><td class="text-secondary" style="padding: 3px 0;">Wildman-Crippen LogP</td><td><b>${mol.logp}</b></td></tr>
                <tr><td class="text-secondary" style="padding: 3px 0;">TPSA</td><td><b>${mol.tpsa} Å²</b></td></tr>
                <tr><td class="text-secondary" style="padding: 3px 0;">HBD / HBA</td><td><b>${mol.hbd} / ${mol.hba}</b></td></tr>
                <tr><td class="text-secondary" style="padding: 3px 0;">Rotatable Bonds</td><td><b>${mol.rotatable_bonds}</b></td></tr>
                <tr><td class="text-secondary" style="padding: 3px 0;">QED Drug-likeness</td><td><b>${mol.qed || '0.50'}</b></td></tr>
                <tr><td class="text-secondary" style="padding: 3px 0;">Descriptor Origin</td><td>${AIDD.getOriginBadge(mol.descriptor_origin || 'COMPUTED')}</td></tr>
              </table>
            </div>
          </div>

          <!-- Right Column: Lineage Timeline & Scientific Pharmacology -->
          <div>
            <h3 style="font-size: 14px; font-weight: 700; color: var(--accent-cyan); margin-bottom: 12px;">Scientific Provenance Timeline</h3>
            <div class="timeline">
              ${timelineHtml}
            </div>

            ${mol.docking_results && mol.docking_results.length > 0 ? `
              <div class="card" style="margin-top: 16px; padding: 12px;">
                <div class="flex justify-between items-center" style="margin-bottom: 6px;">
                  <div class="card-title" style="font-size: 12px; margin-bottom: 0;">Docking Binding Profile</div>
                  ${AIDD.getOriginBadge(mol.docking_results[0].result_origin || 'IMPORTED')}
                </div>
                <div style="font-size: 12px;">
                  <b>Tool:</b> ${mol.docking_results[0].docking_tool} | 
                  <b>Receptor:</b> <code>${mol.docking_results[0].receptor}</code> | 
                  <b>Binding Affinity:</b> <span style="color: #38BDF8; font-weight: 700;">${mol.docking_results[0].docking_score} kcal/mol</span>
                </div>
              </div>
            ` : ''}

            ${mol.admet_results && mol.admet_results.length > 0 ? `
              <div class="card" style="margin-top: 12px; padding: 12px;">
                <div class="flex justify-between items-center" style="margin-bottom: 6px;">
                  <div class="card-title" style="font-size: 12px; margin-bottom: 0;">Pharmacokinetics & ADMET Risk Profile</div>
                  ${AIDD.getOriginBadge(mol.admet_results[0].result_origin || 'IMPORTED')}
                </div>
                <div style="font-size: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                  <div>GI Absorption: <b>${mol.admet_results[0].gi_absorption}</b></div>
                  <div>BBB Permeability: <b>${mol.admet_results[0].bbb_permeant}</b></div>
                  <div>CYP3A4 Inhibition: <b>${mol.admet_results[0].cyp3a4_inhibitor}</b></div>
                  <div>Hepatotoxicity: <b>${mol.admet_results[0].hepatotoxicity}</b></div>
                </div>
                <div style="font-size: 10px; color: var(--text-muted); margin-top: 8px; font-style: italic;">
                  ${mol.admet_results[0].disclaimer}
                </div>
              </div>
            ` : ''}
          </div>
        </div>
      `,
      footer: `<button class="btn btn-secondary" onclick="AIDD.closeModal()">Close</button>`
    });
  },

  // -----------------------------------------------------------------
  // VIEW: DATASETS
  // -----------------------------------------------------------------
  async renderProjectDatasets(container) {
    const proj = this.state.currentProject;
    const datasets = await this.api(`/api/projects/${proj.id}/datasets`);

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Immutable Dataset Lineage</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Git-style immutable dataset snapshots with SHA-256 cryptographic verification</p>
        </div>
        ${datasets.length >= 2 ? `
          <button class="btn btn-secondary" onclick="AIDD.openDatasetCompareModal('${proj.id}')">Compare 2 Versions (Diff)</button>
        ` : ''}
      </div>

      <div class="card" style="padding: 0; overflow: hidden;">
        <div class="table-container" style="border: none;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Dataset Name</th>
                <th>Pipeline Stage</th>
                <th>Compounds</th>
                <th>SHA-256 Checksum</th>
                <th>Created By Experiment</th>
                <th>Timestamp</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${datasets.map(d => `
                <tr class="clickable" onclick="AIDD.openDatasetDetailModal('${d.id}')">
                  <td><code>${d.version_label}</code></td>
                  <td><b>${d.name}</b><br><span style="font-size: 11px; color: var(--text-secondary);">${d.description || ''}</span></td>
                  <td><span class="badge badge-active">${d.stage}</span></td>
                  <td><b>${d.molecule_count}</b></td>
                  <td><code>${(d.sha256_hash || '').substring(0, 12)}...</code></td>
                  <td>${d.experiment_name ? `<code>${d.experiment_name}</code>` : '<span class="text-muted">Direct Import</span>'}</td>
                  <td>${d.created_at.substring(0, 19).replace('T', ' ')}</td>
                  <td>
                    <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); window.open('/api/datasets/${d.id}/export/csv')">Export CSV</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  async openDatasetDetailModal(datasetId) {
    const ds = await this.api(`/api/datasets/${datasetId}`);
    if (!ds) return;

    this.openModal({
      title: `Dataset Snapshot: ${ds.version_label}`,
      large: true,
      body: `
        <div class="flex items-center justify-between mb-4">
          <div>
            <h3 style="font-size: 15px; font-weight: 700;">${ds.name}</h3>
            <p style="color: var(--text-secondary); font-size: 12px;">${ds.description}</p>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
              SHA-256 Hash: <code>${ds.sha256_hash || 'N/A'}</code>
            </div>
          </div>
          <button class="btn btn-primary btn-sm" onclick="window.open('/api/datasets/${ds.id}/export/csv')">Download CSV</button>
        </div>

        <div class="table-container" style="max-height: 420px; overflow-y: auto;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Structure</th>
                <th>ID</th>
                <th>Name</th>
                <th>MW (Da)</th>
                <th>LogP</th>
                <th>TPSA</th>
                <th>Ro5</th>
                <th>Docking</th>
              </tr>
            </thead>
            <tbody>
              ${ds.molecules.map(m => `
                <tr class="clickable" onclick="AIDD.openMoleculeModal('${m.id}')">
                  <td><div class="mol-thumb">${m.svg_structure || ''}</div></td>
                  <td><code>${m.id}</code></td>
                  <td><b>${m.name}</b></td>
                  <td>${m.molecular_weight ? m.molecular_weight.toFixed(1) : ''}</td>
                  <td>${m.logp ? m.logp.toFixed(2) : ''}</td>
                  <td>${m.tpsa ? m.tpsa.toFixed(1) : ''}</td>
                  <td><span class="badge ${m.lipinski_pass ? 'badge-pass' : 'badge-fail'}">${m.lipinski_pass ? 'PASS' : 'FAIL'}</span></td>
                  <td>${m.docking_score ? m.docking_score + ' kcal/mol' : '—'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `,
      footer: `<button class="btn btn-secondary" onclick="AIDD.closeModal()">Close</button>`
    });
  },

  async openDatasetCompareModal(projectId) {
    const datasets = await this.api(`/api/projects/${projectId}/datasets`);
    this.openModal({
      title: 'Compare Dataset Versions (Scientific Diff)',
      body: `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
          <div class="form-group">
            <label class="form-label">Base Dataset (v1)</label>
            <select id="diff-ds-1" class="form-control">
              ${datasets.map(d => `<option value="${d.id}">${d.version_label} (${d.molecule_count} mols)</option>`).join('')}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Target Dataset (v2)</label>
            <select id="diff-ds-2" class="form-control">
              ${datasets.map((d, i) => `<option value="${d.id}" ${i === datasets.length - 1 ? 'selected' : ''}>${d.version_label} (${d.molecule_count} mols)</option>`).join('')}
            </select>
          </div>
        </div>
        <div id="diff-results-area" style="margin-top: 14px;"></div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Close</button>
        <button class="btn btn-primary" onclick="AIDD.executeDatasetDiff()">Compute Diff</button>
      `
    });
  },

  async executeDatasetDiff() {
    const id1 = document.getElementById('diff-ds-1').value;
    const id2 = document.getElementById('diff-ds-2').value;
    const res = await this.api(`/api/datasets/compare?id1=${id1}&id2=${id2}`);
    const area = document.getElementById('diff-results-area');

    area.innerHTML = `
      <div class="metric-grid" style="margin-bottom: 14px;">
        <div class="metric-card"><div class="metric-label">Common Compounds</div><div class="metric-value" style="color: #10B981;">${res.common_count}</div></div>
        <div class="metric-card"><div class="metric-label">Filtered / Excluded</div><div class="metric-value" style="color: #EF4444;">${res.removed_count}</div></div>
        <div class="metric-card"><div class="metric-label">Added</div><div class="metric-value" style="color: #38BDF8;">${res.added_count}</div></div>
      </div>
      ${res.removed_molecules && res.removed_molecules.length > 0 ? `
        <div class="card" style="padding: 10px; margin-bottom: 0;">
          <div class="card-title" style="font-size: 12px; color: #EF4444;">Molecules Excluded in ${res.dataset_2.version_label}</div>
          <table class="data-table" style="font-size: 11px;">
            <thead><tr><th>ID</th><th>Name</th><th>MW</th><th>LogP</th><th>Ro5</th></tr></thead>
            <tbody>
              ${res.removed_molecules.map(m => `
                <tr><td><code>${m.id}</code></td><td>${m.name}</td><td>${m.molecular_weight}</td><td>${m.logp}</td><td>${m.lipinski_violations} violations</td></tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : ''}
    `;
  },

  // -----------------------------------------------------------------
  // VIEW: EXPERIMENTS & REPRODUCTION
  // -----------------------------------------------------------------
  async renderProjectExperiments(container) {
    const proj = this.state.currentProject;
    const experiments = await this.api(`/api/projects/${proj.id}/experiments`);

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Experiment Run History</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Locked & immutable experiment logs with execution manifests and reproduction checks</p>
        </div>
        <button class="btn btn-primary" onclick="AIDD.openNewExperimentModal('${proj.id}')">+ New Experiment</button>
      </div>

      <div class="card" style="padding: 0; overflow: hidden;">
        <div class="table-container" style="border: none;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Experiment Name</th>
                <th>Pipeline Stage</th>
                <th>Tool & Version</th>
                <th>Input Dataset</th>
                <th>Output Dataset</th>
                <th>Throughput</th>
                <th>Duration</th>
                <th>Lock</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${experiments.map(e => `
                <tr class="clickable" onclick="AIDD.openExperimentModal('${e.id}')">
                  <td>
                    <b>${e.name}</b><br>
                    <code style="font-size: 10px;">${e.id}</code>
                    ${e.reproduction_of_id ? `<span class="badge badge-active" style="font-size: 9px;">Reproduction of ${e.reproduction_of_id}</span>` : ''}
                  </td>
                  <td><span class="badge badge-active">${e.stage}</span></td>
                  <td><code>${e.tool} v${e.tool_version}</code></td>
                  <td>${e.input_dataset_label ? `<code>${e.input_dataset_label}</code>` : '<span class="text-muted">—</span>'}</td>
                  <td>${e.output_dataset_label ? `<code>${e.output_dataset_label}</code>` : '<span class="text-muted">—</span>'}</td>
                  <td>${e.molecules_in} in / ${e.molecules_out} out ${e.molecules_failed > 0 ? `<span style="color: #EF4444; font-weight: 700;">(${e.molecules_failed} fail)</span>` : ''}</td>
                  <td>${e.duration_seconds}s</td>
                  <td><span class="badge badge-locked">🔒 Locked</span></td>
                  <td><span class="badge badge-${e.status}">${e.status}</span></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  async openExperimentModal(expId) {
    const exp = await this.api(`/api/experiments/${expId}`);
    if (!exp) return;

    const paramsHtml = Object.entries(exp.parameters || {}).map(([k, v]) => `
      <tr><td class="text-secondary" style="padding: 4px 8px; width: 35%;"><code>${k}</code></td><td style="padding: 4px 8px;"><b>${typeof v === 'object' ? JSON.stringify(v) : v}</b></td></tr>
    `).join('');

    const failuresHtml = (exp.failures || []).map(f => `
      <tr>
        <td><code>${f.molecule_id || 'N/A'}</code></td>
        <td><b>${f.molecule_name || 'Unknown'}</b></td>
        <td><span class="badge badge-fail">${f.error_type}</span></td>
        <td>${f.error_message}</td>
      </tr>
    `).join('');

    const artifactsHtml = (exp.artifacts || []).map(a => `
      <tr>
        <td><b>${a.name}</b></td>
        <td><code>${a.file_type}</code></td>
        <td>${a.file_size_bytes} B</td>
        <td><code>${(a.sha256_hash || '').substring(0, 16)}...</code></td>
      </tr>
    `).join('');

    this.openModal({
      title: `Experiment: ${exp.name} (${exp.id})`,
      large: true,
      body: `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 12px;">
          <div style="display: flex; gap: 10px; align-items: center;">
            <span class="badge badge-locked">🔒 Immutable Record</span>
            <div><b>Stage:</b> <span class="badge badge-active">${exp.stage}</span></div>
            <div><b>Tool:</b> <code>${exp.tool} v${exp.tool_version}</code></div>
            <div><b>Status:</b> <span class="badge badge-${exp.status}">${exp.status}</span></div>
          </div>
          <div class="flex gap-2">
            <button class="btn btn-secondary btn-sm" onclick="window.open('/api/experiments/${exp.id}/manifest')">📋 Export Manifest (JSON)</button>
            <button class="btn btn-primary btn-sm" onclick="AIDD.triggerReproduction('${exp.id}')">🔄 Reproduce Experiment</button>
          </div>
        </div>

        <!-- 2 Columns: Parameters & Environment -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
          <div class="card" style="margin-bottom: 0; padding: 12px;">
            <div class="card-title" style="font-size: 12px; margin-bottom: 8px;">Execution Parameters</div>
            <table style="width: 100%; font-size: 11.5px; border-collapse: collapse;">
              ${paramsHtml}
            </table>
          </div>
          <div class="card" style="margin-bottom: 0; padding: 12px;">
            <div class="card-title" style="font-size: 12px; margin-bottom: 8px;">Execution Environment</div>
            <table style="width: 100%; font-size: 11.5px; border-collapse: collapse;">
              <tr><td class="text-secondary" style="padding: 3px 0;">OS</td><td>${exp.environment_info.os || 'Linux 6.6'}</td></tr>
              <tr><td class="text-secondary" style="padding: 3px 0;">Python</td><td>${exp.environment_info.python_version || '3.11.2'}</td></tr>
              <tr><td class="text-secondary" style="padding: 3px 0;">Cheminformatics</td><td>${exp.environment_info.cheminformatics_engine || 'RDKit Native'}</td></tr>
            </table>
          </div>
        </div>

        <!-- Failures Section -->
        ${exp.failures && exp.failures.length > 0 ? `
          <div class="card" style="border: 1px solid rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.04); margin-bottom: 16px;">
            <div class="card-header" style="border-color: rgba(239, 68, 68, 0.2);">
              <div class="card-title" style="color: #EF4444; font-size: 13px;">
                ⚠️ Failure Log (${exp.failures.length} Molecules Excluded)
              </div>
              <button class="btn btn-danger btn-sm" onclick="window.open('/api/experiments/${exp.id}/failures/csv')">
                Export Failures CSV
              </button>
            </div>
            <div class="table-container" style="border: none; background: transparent;">
              <table class="data-table">
                <thead>
                  <tr><th>Molecule ID</th><th>Name</th><th>Error Type</th><th>Scientific Reason</th></tr>
                </thead>
                <tbody>
                  ${failuresHtml}
                </tbody>
              </table>
            </div>
          </div>
        ` : ''}

        <!-- Artifacts with SHA-256 -->
        ${exp.artifacts && exp.artifacts.length > 0 ? `
          <div class="card" style="padding: 12px; margin-bottom: 16px;">
            <div class="card-title" style="font-size: 12px; margin-bottom: 8px;">Artifacts & Cryptographic Checksums (SHA-256)</div>
            <table class="data-table">
              <thead><tr><th>File Name</th><th>Type</th><th>Size</th><th>SHA-256 Hash</th></tr></thead>
              <tbody>${artifactsHtml}</tbody>
            </table>
          </div>
        ` : ''}

        <!-- Execution Logs -->
        <div class="card" style="padding: 12px; margin-bottom: 0;">
          <div class="card-title" style="font-size: 12px; margin-bottom: 8px;">Execution Logs</div>
          <pre class="code-block">${exp.logs || 'No logs recorded.'}</pre>
        </div>
      `,
      footer: `<button class="btn btn-secondary" onclick="AIDD.closeModal()">Close</button>`
    });
  },

  async triggerReproduction(expId) {
    this.showToast('Executing experiment reproduction...', 'info');
    const res = await this.api(`/api/experiments/${expId}/reproduce`, { method: 'POST' });
    this.closeModal();
    if (res.reproduction_match) {
      this.showToast(`Reproduction succeeded! Output metrics match 100% (New Exp: ${res.reproduced_experiment_id})`, 'success');
    } else {
      this.showToast(`Reproduction diverged: ${res.diff_reasons.join(', ')}`, 'error');
    }
    this.render();
  },

  // -----------------------------------------------------------------
  // VIEW: CANDIDATE SELECTION & WEIGHTED RANKING
  // -----------------------------------------------------------------
  async renderProjectCandidates(container) {
    const proj = this.state.currentProject;
    const candidates = await this.api(`/api/projects/${proj.id}/candidates`);

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Candidate Selection & Ranking</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Mathematically transparent multi-parameter scoring with explicit normalization and missing data handling</p>
        </div>
        <button class="btn btn-primary" onclick="AIDD.openWeightsModal('${proj.id}')">⚙️ Configure Weights & Policy</button>
      </div>

      <!-- Transparent Equation Card -->
      <div class="card" style="border-left: 4px solid #8B5CF6; background: #0F172A;">
        <div class="form-label" style="color: #A78BFA;">Mathematical Optimization Model</div>
        <div style="font-family: var(--font-mono); font-size: 13px; color: #F8FAFC; margin-top: 4px;">
          ${candidates.length > 0 && candidates[0].formula_expression ? candidates[0].formula_expression : 'Composite Score = (35.0% * Dock_Norm) + (25.0% * QSAR_Norm) + (25.0% * ADMET_Norm) + (15.0% * QED_Norm)'}
        </div>
        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 6px;">
          Normalization: <b>${candidates.length > 0 && candidates[0].normalization_method ? candidates[0].normalization_method : 'Min-Max Inverted Docking, pIC50 QSAR, Categorical ADMET, QED'}</b> • Missing Data Policy: <b>${candidates.length > 0 ? (candidates[0].missing_data_policy || 'RENORMALIZE') : 'RENORMALIZE'}</b>
        </div>
      </div>

      <!-- Ranked Candidates Table -->
      <div class="card" style="padding: 0; overflow: hidden;">
        <div class="table-container" style="border: none;">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px;">Rank</th>
                <th>Structure</th>
                <th>Molecule</th>
                <th>Composite Score</th>
                <th>Docking Affinity</th>
                <th>ADMET Safety</th>
                <th>MW (Da)</th>
                <th>LogP</th>
                <th>TPSA</th>
                <th>Candidate Tier</th>
                <th>Origin</th>
              </tr>
            </thead>
            <tbody>
              ${candidates.map(c => `
                <tr class="clickable" onclick="AIDD.openMoleculeModal('${c.molecule_id}')">
                  <td><b style="font-size: 14px; color: ${c.rank_position <= 3 ? '#F59E0B' : '#94A3B8'};">#${c.rank_position}</b></td>
                  <td><div class="mol-thumb">${c.svg_structure || ''}</div></td>
                  <td><b>${c.molecule_name}</b><br><code style="font-size: 10px;">${c.molecule_id}</code></td>
                  <td>
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <b style="font-size: 13px; color: #38BDF8;">${c.composite_score.toFixed(1)}</b>
                      <div style="width: 60px; height: 6px; background: #1E293B; border-radius: 3px; overflow: hidden;">
                        <div style="width: ${c.composite_score}%; height: 100%; background: #38BDF8;"></div>
                      </div>
                    </div>
                  </td>
                  <td><code>${c.docking_score !== null ? c.docking_score.toFixed(1) + ' kcal/mol' : 'N/A'}</code></td>
                  <td><span class="badge ${c.admet_risk_level === 'Low Risk' ? 'badge-low-risk' : (c.admet_risk_level === 'Moderate Risk' ? 'badge-moderate-risk' : 'badge-high-risk')}">${c.admet_risk_level || 'N/A'}</span></td>
                  <td>${c.molecular_weight ? c.molecular_weight.toFixed(1) : ''}</td>
                  <td>${c.logp ? c.logp.toFixed(2) : ''}</td>
                  <td>${c.tpsa ? c.tpsa.toFixed(1) : ''}</td>
                  <td><span class="badge ${c.tier === 'Lead Candidate' ? 'badge-lead' : 'badge-backup'}">${c.tier}</span></td>
                  <td>${AIDD.getOriginBadge(c.result_origin || 'COMPUTED')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  openWeightsModal(projectId) {
    this.openModal({
      title: 'Configure Multi-Objective Weights & Missing Data Policy',
      body: `
        <div style="display: flex; flex-direction: column; gap: 16px;">
          <div>
            <div class="flex justify-between font-label" style="font-size: 12px; margin-bottom: 4px;">
              <span>Docking Affinity Weight</span>
              <b id="val-dock">35%</b>
            </div>
            <input type="range" id="w-dock" min="0" max="100" value="35" class="form-control" oninput="document.getElementById('val-dock').innerText = this.value + '%'">
          </div>
          <div>
            <div class="flex justify-between font-label" style="font-size: 12px; margin-bottom: 4px;">
              <span>QSAR Bioactivity Prediction Weight</span>
              <b id="val-qsar">25%</b>
            </div>
            <input type="range" id="w-qsar" min="0" max="100" value="25" class="form-control" oninput="document.getElementById('val-qsar').innerText = this.value + '%'">
          </div>
          <div>
            <div class="flex justify-between font-label" style="font-size: 12px; margin-bottom: 4px;">
              <span>ADMET Safety Profile Weight</span>
              <b id="val-admet">25%</b>
            </div>
            <input type="range" id="w-admet" min="0" max="100" value="25" class="form-control" oninput="document.getElementById('val-admet').innerText = this.value + '%'">
          </div>
          <div>
            <div class="flex justify-between font-label" style="font-size: 12px; margin-bottom: 4px;">
              <span>QED Drug-Likeness Weight</span>
              <b id="val-qed">15%</b>
            </div>
            <input type="range" id="w-qed" min="0" max="100" value="15" class="form-control" oninput="document.getElementById('val-qed').innerText = this.value + '%'">
          </div>

          <div class="form-group" style="margin-top: 10px;">
            <label class="form-label">Missing Data Policy</label>
            <select id="missing-policy" class="form-control">
              <option value="RENORMALIZE">RENORMALIZE (Renormalize available weights, flag candidate)</option>
              <option value="EXCLUDE">EXCLUDE (Exclude incomplete candidates from final ranking)</option>
              <option value="PENALIZE_DEFAULT">PENALIZE_DEFAULT (Assign neutral 0.3 penalty for missing terms)</option>
            </select>
          </div>
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="AIDD.saveCustomRanking('${projectId}')">Apply & Re-Rank Candidates</button>
      `
    });
  },

  async saveCustomRanking(projectId) {
    const d = parseFloat(document.getElementById('w-dock').value);
    const q = parseFloat(document.getElementById('w-qsar').value);
    const a = parseFloat(document.getElementById('w-admet').value);
    const qed = parseFloat(document.getElementById('w-qed').value);
    const policy = document.getElementById('missing-policy').value;

    await this.api(`/api/projects/${projectId}/experiments/candidates/rank`, {
      method: 'POST',
      body: JSON.stringify({
        weights: { docking: d, qsar: q, admet: a, druglikeness: qed },
        missing_data_policy: policy,
        experiment_name: `Custom Multi-Parameter Ranking (${d}/${q}/${a}/${qed})`,
        notes: `Applied policy: ${policy}`
      })
    });

    this.closeModal();
    this.showToast('Candidate rankings re-computed successfully', 'success');
    this.render();
  },

  // -----------------------------------------------------------------
  // VIEW: PROVENANCE DAG GRAPH
  // -----------------------------------------------------------------
  async renderProjectProvenance(container) {
    const proj = this.state.currentProject;
    const graphData = await this.api(`/api/projects/${proj.id}/provenance`);

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Interactive Provenance DAG</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Full scientific lineage connecting datasets, experiments, models, and candidates</p>
        </div>
      </div>

      <div id="provenance-canvas-container"></div>
    `;

    setTimeout(() => {
      AIDDProvenance.init('provenance-canvas-container', graphData, (node) => {
        if (node.type === 'dataset') {
          AIDD.openDatasetDetailModal(node.id);
        } else if (node.type === 'experiment') {
          AIDD.openExperimentModal(node.id);
        } else if (node.type === 'candidate_set') {
          AIDD.navigate('project-candidates', proj.id);
        }
      });
    }, 50);
  },

  // -----------------------------------------------------------------
  // VIEW: DECISION LOG
  // -----------------------------------------------------------------
  async renderProjectDecisions(container) {
    const proj = this.state.currentProject;
    const decisions = await this.api(`/api/projects/${proj.id}/decisions`);

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Research Decision Log</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Scientific audit trail recording researcher intent, filtering rationales, and hypothesis shifts</p>
        </div>
        <button class="btn btn-primary" onclick="AIDD.openNewDecisionModal('${proj.id}')">+ Log Scientific Decision</button>
      </div>

      <div style="display: flex; flex-direction: column; gap: 12px;">
        ${decisions.map(d => `
          <div class="card" style="margin-bottom: 0;">
            <div class="flex justify-between items-center" style="margin-bottom: 8px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <h3 style="font-size: 14px; font-weight: 700;">${d.title}</h3>
                <span class="badge badge-active">${d.stage || 'Pipeline'}</span>
              </div>
              <span style="font-size: 11px; color: var(--text-muted);">${d.created_at.substring(0, 10)}</span>
            </div>
            <div style="font-size: 13px; color: #F1F5F9; margin-bottom: 6px;">
              <b>Decision:</b> ${d.decision_text}
            </div>
            <div style="font-size: 12.5px; color: var(--text-secondary); margin-bottom: 10px;">
              <b>Scientific Rationale:</b> ${d.rationale}
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 8px; border-top: 1px solid var(--border-subtle); font-size: 11px; color: var(--text-muted);">
              <span><b>Author:</b> ${d.author}</span>
              <span>${d.related_experiment_name ? `Linked to <code>${d.related_experiment_name}</code>` : ''}</span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  },

  openNewDecisionModal(projectId) {
    this.openModal({
      title: 'Log New Research Decision',
      body: `
        <div class="form-group">
          <label class="form-label">Decision Title</label>
          <input type="text" id="dec-title" class="form-control" placeholder="e.g. Exclude covalent warheads for wild-type screen">
        </div>
        <div class="form-group">
          <label class="form-label">Specific Decision Action</label>
          <textarea id="dec-text" class="form-control" placeholder="Describe the concrete decision or filter applied..."></textarea>
        </div>
        <div class="form-group">
          <label class="form-label">Scientific Rationale & Hypothesis</label>
          <textarea id="dec-rationale" class="form-control" placeholder="Explain WHY this decision was made..."></textarea>
        </div>
        <div class="form-group">
          <label class="form-label">Author / Chemist</label>
          <input type="text" id="dec-author" class="form-control" value="Lead Medicinal Chemist">
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="AIDD.saveDecision('${projectId}')">Save Decision</button>
      `
    });
  },

  async saveDecision(projectId) {
    const title = document.getElementById('dec-title').value;
    const text = document.getElementById('dec-text').value;
    const rationale = document.getElementById('dec-rationale').value;
    const author = document.getElementById('dec-author').value;

    if (!title || !text) {
      this.showToast('Title and decision text are required', 'error');
      return;
    }

    await this.api(`/api/projects/${projectId}/decisions`, {
      method: 'POST',
      body: JSON.stringify({
        title,
        decision_text: text,
        rationale: rationale || 'Researcher discretion.',
        author,
        stage: 'Candidate Selection'
      })
    });

    this.closeModal();
    this.showToast('Research decision recorded', 'success');
    this.render();
  },

  // -----------------------------------------------------------------
  // VIEW: REPRODUCIBILITY REPORT
  // -----------------------------------------------------------------
  async renderProjectReport(container) {
    const proj = this.state.currentProject;

    container.innerHTML = `
      <div class="flex items-center justify-between mb-4">
        <div>
          <h1 style="font-size: 20px; font-weight: 700;">Reproducibility Research Report</h1>
          <p style="color: var(--text-secondary); font-size: 13px;">Full verifiable audit report generated directly from immutable provenance records</p>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-secondary" onclick="window.open('/api/projects/${proj.id}/reproducibility-bundle')">📦 Download ZIP Bundle</button>
          <button class="btn btn-primary" onclick="window.open('/api/projects/${proj.id}/report?format=html')">📄 Open Printable HTML Report</button>
        </div>
      </div>

      <div class="card" style="height: 620px; padding: 0; overflow: hidden;">
        <iframe src="/api/projects/${proj.id}/report?format=html" style="width: 100%; height: 100%; border: none;"></iframe>
      </div>
    `;
  },

  // -----------------------------------------------------------------
  // SCIENTIFIC REGRESSION AUDIT MODAL
  // -----------------------------------------------------------------
  async openAuditModal() {
    const audit = await this.api('/api/scientific/audit');
    const eng = audit.engine_status;

    this.openModal({
      title: '🔬 Scientific Engine Regression Audit',
      large: true,
      body: `
        <div style="margin-bottom: 16px; padding: 12px; background: #0F172A; border-radius: 6px; border: 1px solid var(--border-subtle);">
          <div style="font-size: 13px; font-weight: 700; color: #F8FAFC;">Active Computational Kernel: ${eng.active_engine}</div>
          <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;">${eng.engine_notice}</div>
        </div>

        <div class="metric-grid" style="margin-bottom: 16px;">
          <div class="metric-card">
            <div class="metric-label">Benchmark Result</div>
            <div class="metric-value" style="color: ${audit.all_passed ? '#10B981' : '#EF4444'};">
              ${audit.all_passed ? '100% PASSED' : 'FAILURES DETECTED'}
            </div>
            <div class="metric-subtext">${audit.passed_count} / ${audit.compounds_tested} reference standards verified</div>
          </div>
        </div>

        <div class="card" style="padding: 0; overflow: hidden;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Compound</th>
                <th>SMILES</th>
                <th>Formula</th>
                <th>MW (Da)</th>
                <th>LogP</th>
                <th>TPSA</th>
                <th>HBD / HBA</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${audit.details.map(d => `
                <tr>
                  <td><b>${d.compound.toUpperCase()}</b></td>
                  <td><code>${d.smiles}</code></td>
                  <td><code>${d.formula.calculated}</code></td>
                  <td>${d.molecular_weight.calculated}</td>
                  <td>${d.logp.calculated}</td>
                  <td>${d.tpsa.calculated}</td>
                  <td>${d.hbd.calculated} / ${d.hba.calculated}</td>
                  <td><span class="badge ${d.passed ? 'badge-pass' : 'badge-fail'}">${d.passed ? 'PASS' : 'FAIL'}</span></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `,
      footer: `<button class="btn btn-secondary" onclick="AIDD.closeModal()">Close Audit</button>`
    });
  },

  // -----------------------------------------------------------------
  // MODALS & EXPERIMENT RUN LAUNCHERS
  // -----------------------------------------------------------------
  openModal({ title, body, footer, large = false }) {
    this.closeModal();
    const modal = document.createElement('div');
    modal.className = 'modal-backdrop';
    modal.id = 'active-modal';
    modal.innerHTML = `
      <div class="modal-dialog ${large ? 'modal-dialog-lg' : ''}">
        <div class="modal-header">
          <div class="modal-title">${title}</div>
          <button class="modal-close" onclick="AIDD.closeModal()">&times;</button>
        </div>
        <div class="modal-body">
          ${body}
        </div>
        ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
      </div>
    `;
    document.body.appendChild(modal);
  },

  closeModal() {
    const m = document.getElementById('active-modal');
    if (m) m.remove();
  },

  openNewProjectModal() {
    this.openModal({
      title: 'Create New Research Project',
      body: `
        <div class="form-group">
          <label class="form-label">Project Name</label>
          <input type="text" id="new-proj-name" class="form-control" placeholder="e.g. KRAS G12D Small Molecule Discovery">
        </div>
        <div class="form-group">
          <label class="form-label">Target Protein / Receptor</label>
          <input type="text" id="new-proj-target" class="form-control" placeholder="e.g. KRAS G12D Switch II Pocket (PDB: 7RPZ)">
        </div>
        <div class="form-group">
          <label class="form-label">Disease / Indication</label>
          <input type="text" id="new-proj-disease" class="form-control" placeholder="e.g. Pancreatic Ductal Adenocarcinoma">
        </div>
        <div class="form-group">
          <label class="form-label">Scientific Hypothesis</label>
          <textarea id="new-proj-hypo" class="form-control" placeholder="State the structural or pharmacological hypothesis..."></textarea>
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="AIDD.createProjectSubmit()">Create Project</button>
      `
    });
  },

  async createProjectSubmit() {
    const name = document.getElementById('new-proj-name').value;
    const target = document.getElementById('new-proj-target').value;
    const disease = document.getElementById('new-proj-disease').value;
    const hypo = document.getElementById('new-proj-hypo').value;

    if (!name.trim()) {
      this.showToast('Project name is required', 'error');
      return;
    }

    const proj = await this.api('/api/projects', {
      method: 'POST',
      body: JSON.stringify({
        name,
        target_protein: target,
        disease_indication: disease,
        hypothesis: hypo
      })
    });

    await this.loadProjects();
    this.closeModal();
    this.showToast(`Project '${proj.name}' created`, 'success');
    this.navigate('project-overview', proj.id);
  },

  openProjectSwitchModal() {
    this.openModal({
      title: 'Switch Research Project',
      body: `
        <div style="display: flex; flex-direction: column; gap: 8px;">
          ${this.state.projects.map(p => `
            <div class="card clickable" style="margin-bottom: 0; padding: 12px;" onclick="AIDD.closeModal(); AIDD.navigate('project-overview', '${p.id}')">
              <div class="flex justify-between items-center">
                <b>${p.name}</b>
                <span class="badge badge-active">${p.current_stage}</span>
              </div>
              <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                ${p.target_protein || 'Target N/A'} • ${p.molecule_count || 0} molecules
              </div>
            </div>
          `).join('')}
        </div>
      `,
      footer: `<button class="btn btn-primary btn-sm" onclick="AIDD.openNewProjectModal()">+ Create New Project</button>`
    });
  },

  openImportModal(projectId) {
    this.openModal({
      title: 'Import Molecules to Pipeline',
      large: true,
      body: `
        <div class="form-group">
          <label class="form-label">Input Format</label>
          <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">
            Paste CSV formatted text with columns <code>molecule_id,molecule_name,smiles</code>.
          </div>
          <textarea id="import-csv-text" class="form-control form-control-mono" style="min-height: 180px;" placeholder="molecule_id,molecule_name,smiles&#10;LIG-101,Aspirin,CC(=O)Oc1ccccc1C(=O)O&#10;LIG-102,Paracetamol,CC(=O)Nc1ccc(O)cc1&#10;LIG-103,Caffeine,CN1C=NC2=C1C(=O)N(C(=O)N2C)C"></textarea>
        </div>
        <div class="flex gap-2 mb-4">
          <button class="btn btn-secondary btn-sm" onclick="document.getElementById('import-csv-text').value = 'molecule_id,molecule_name,smiles\\nLIG-001,Osimertinib,C=CC(=O)Nc1cc(Nc2nccc(n2)c3cn(C)c4ccccc34)c(OC)cc1N(C)CCN(C)C\\nLIG-002,Gefitinib,COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1\\nLIG-003,Erlotinib,COCCOC1=C(C=C2C(=C1)C(=NC=N2)NC3=CC=CC(=C3)C#C)OCCOC\\nLIG-FAIL,BadRadical,c1ccccc1[N+](=O)(=O)C(F)(F)(F)(F)'">
            Insert Sample CSV (With Test Failure)
          </button>
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="AIDD.submitImport('${projectId}')">Parse & Ingest Molecules</button>
      `
    });
  },

  async submitImport(projectId) {
    const text = document.getElementById('import-csv-text').value;
    if (!text.trim()) {
      this.showToast('Please provide CSV or SMILES content', 'error');
      return;
    }

    const res = await this.api(`/api/projects/${projectId}/molecules/import`, {
      method: 'POST',
      body: JSON.stringify({ csv_text: text })
    });

    this.closeModal();
    this.showToast(`Imported ${res.total_parsed} compounds (${res.total_failed} failures tracked)`, 'success');
    this.render();
  },

  openPreprocessModal(projectId, datasetId) {
    this.openModal({
      title: 'Run Standardization & Desalting Experiment',
      body: `
        <div class="form-group">
          <label class="form-label">Experiment Name</label>
          <input type="text" id="prep-name" class="form-control" value="Standardization & Desalting">
        </div>
        <div class="form-group">
          <label class="form-label">Max Molecular Weight (Da)</label>
          <input type="number" id="prep-mw" class="form-control" value="650.0">
        </div>
        <div class="form-group">
          <label class="form-label">Max LogP</label>
          <input type="number" id="prep-logp" class="form-control" value="6.8">
        </div>
        <div class="form-group">
          <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary);">
            <input type="checkbox" id="prep-salts" checked>
            Strip Inorganic Counterions & Salts (Keep Largest Fragment)
          </label>
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="AIDD.submitPreprocessing('${projectId}', '${datasetId}')">Execute Standardization</button>
      `
    });
  },

  async submitPreprocessing(projectId, datasetId) {
    const name = document.getElementById('prep-name').value;
    const mw = parseFloat(document.getElementById('prep-mw').value);
    const logp = parseFloat(document.getElementById('prep-logp').value);
    const salts = document.getElementById('prep-salts').checked;

    await this.api(`/api/projects/${projectId}/molecules/standardize`, {
      method: 'POST',
      body: JSON.stringify({
        input_dataset_id: datasetId,
        experiment_name: name,
        max_mw: mw,
        max_logp: logp,
        remove_salts: salts
      })
    });

    this.closeModal();
    this.showToast('Standardization experiment completed successfully', 'success');
    this.render();
  },

  openDockingModal(projectId, datasetId) {
    this.openModal({
      title: 'Import / Run Molecular Docking (AutoDock Vina)',
      body: `
        <div class="form-group">
          <label class="form-label">Data Origin</label>
          <select id="dock-origin" class="form-control">
            <option value="IMPORTED">IMPORTED (Real AutoDock Vina Result File)</option>
            <option value="SIMULATED">SIMULATED (In Silico Physics Model)</option>
            <option value="DEMO">DEMO (Pre-calculated Benchmark)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Docking Tool & Version</label>
          <input type="text" id="dock-tool" class="form-control" value="AutoDock Vina v1.2.5">
        </div>
        <div class="form-group">
          <label class="form-label">Receptor Target</label>
          <input type="text" id="dock-receptor" class="form-control" value="EGFR Kinase Domain (PDB: 4WKQ)">
        </div>
        <div class="form-group">
          <label class="form-label">Grid Center Coordinates (x, y, z)</label>
          <input type="text" id="dock-grid" class="form-control" value="center_x=22.4, y=0.8, z=52.5">
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="AIDD.submitDocking('${projectId}', '${datasetId}')">Record Docking Screen</button>
      `
    });
  },

  async submitDocking(projectId, datasetId) {
    const origin = document.getElementById('dock-origin').value;
    const tool = document.getElementById('dock-tool').value;
    const receptor = document.getElementById('dock-receptor').value;
    const grid = document.getElementById('dock-grid').value;

    await this.api(`/api/projects/${projectId}/experiments/docking`, {
      method: 'POST',
      body: JSON.stringify({
        input_dataset_id: datasetId,
        docking_tool: tool,
        receptor: receptor,
        grid_center: grid,
        result_origin: origin
      })
    });

    this.closeModal();
    this.showToast('Docking screen registered with scientific origin tag', 'success');
    this.render();
  },

  openADMETModal(projectId, datasetId) {
    this.openModal({
      title: 'Import / Run In Silico ADMET Evaluation',
      body: `
        <div class="form-group">
          <label class="form-label">Data Origin</label>
          <select id="admet-origin" class="form-control">
            <option value="IMPORTED">IMPORTED (SwissADME / pkCSM Export File)</option>
            <option value="SIMULATED">SIMULATED (In Silico Rule Consensus)</option>
            <option value="DEMO">DEMO (Pre-calculated Benchmark)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Profiling Engine / Provider</label>
          <input type="text" id="admet-tool" class="form-control" value="SwissADME & pkCSM Engine">
        </div>
      `,
      footer: `
        <button class="btn btn-secondary" onclick="AIDD.closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="AIDD.submitADMET('${projectId}', '${datasetId}')">Record ADMET Profiling</button>
      `
    });
  },

  async submitADMET(projectId, datasetId) {
    const origin = document.getElementById('admet-origin').value;
    const tool = document.getElementById('admet-tool').value;
    await this.api(`/api/projects/${projectId}/experiments/admet`, {
      method: 'POST',
      body: JSON.stringify({
        input_dataset_id: datasetId,
        tool_name: tool,
        result_origin: origin
      })
    });

    this.closeModal();
    this.showToast('ADMET profiling recorded with origin tagging', 'success');
    this.render();
  },

  openNewExperimentModal(projectId) {
    this.openModal({
      title: 'Launch Pipeline Experiment',
      body: `
        <div class="form-group">
          <label class="form-label">Select Pipeline Stage</label>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <button class="btn btn-secondary" style="justify-content: flex-start;" onclick="AIDD.closeModal(); AIDD.openPreprocessModal('${projectId}')">
              ⚙️ Standardization & Desalting Experiment
            </button>
            <button class="btn btn-secondary" style="justify-content: flex-start;" onclick="AIDD.closeModal(); AIDD.openDockingModal('${projectId}')">
              🎯 AutoDock Vina Docking Screen / Import
            </button>
            <button class="btn btn-secondary" style="justify-content: flex-start;" onclick="AIDD.closeModal(); AIDD.openADMETModal('${projectId}')">
              🧬 In Silico ADMET & Safety Evaluation
            </button>
            <button class="btn btn-secondary" style="justify-content: flex-start;" onclick="AIDD.closeModal(); AIDD.openWeightsModal('${projectId}')">
              🏆 Candidate Multi-Parameter Ranking
            </button>
          </div>
        </div>
      `
    });
  },

  async resetDemoData() {
    await this.api('/api/demo/reset', { method: 'POST' });
    await this.loadProjects();
    this.showToast('EGFR Inhibitor Discovery demo project reloaded', 'success');
    this.navigate('project-overview', 'proj_egfr_demo');
  }
};

window.addEventListener('DOMContentLoaded', () => {
  AIDD.init();
});