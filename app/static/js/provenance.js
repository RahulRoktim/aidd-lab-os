/**
 * AIDD Lab OS - Interactive Provenance DAG Visualizer
 * Pure vector SVG graph renderer with topological layout, pan/zoom, and node inspector.
 */

window.AIDDProvenance = {
  container: null,
  svg: null,
  g: null,
  data: { nodes: [], edges: [] },
  transform: { x: 40, y: 40, k: 1.0 },
  isDragging: false,
  dragStart: { x: 0, y: 0 },
  selectedNode: null,

  init(containerId, data, onNodeClick) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;
    this.data = data;
    this.onNodeClick = onNodeClick;
    this.render();
    this.bindEvents();
  },

  render() {
    this.container.innerHTML = `
      <div class="prov-toolbar">
        <button class="btn btn-secondary btn-sm" id="prov-zoom-in" title="Zoom In">+</button>
        <button class="btn btn-secondary btn-sm" id="prov-zoom-out" title="Zoom Out">-</button>
        <button class="btn btn-secondary btn-sm" id="prov-reset" title="Fit to View">Fit</button>
      </div>
      <svg id="prov-svg" width="100%" height="100%" style="cursor: grab;">
        <defs>
          <marker id="arrow-dataset" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="#38BDF8" />
          </marker>
          <marker id="arrow-experiment" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="#10B981" />
          </marker>
          <marker id="arrow-default" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748B" />
          </marker>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
        <g id="prov-viewport"></g>
      </svg>
    `;

    this.svg = document.getElementById('prov-svg');
    this.g = document.getElementById('prov-viewport');

    this.layoutNodes();
    this.drawGraph();
    this.updateTransform();
  },

  layoutNodes() {
    // Topological stage columns
    const stageColumns = {
      "Dataset": 0,
      "Preprocessing": 1,
      "Descriptor Generation": 2,
      "Docking": 3,
      "ADMET": 4,
      "Candidate Selection": 5
    };

    const colWidth = 260;
    const rowHeight = 130;
    const colCounters = [0, 0, 0, 0, 0, 0];

    const nodeMap = {};

    this.data.nodes.forEach(node => {
      let col = stageColumns[node.stage] !== undefined ? stageColumns[node.stage] : 0;
      if (node.type === 'candidate_set') col = 5;

      const row = colCounters[col];
      colCounters[col] += 1;

      node.x = col * colWidth + 50;
      node.y = row * rowHeight + 60;
      node.width = 200;
      node.height = 76;

      nodeMap[node.id] = node;
    });

    this.nodeMap = nodeMap;
  },

  drawGraph() {
    let html = '';

    // Draw Edges
    this.data.edges.forEach(edge => {
      const src = this.nodeMap[edge.source];
      const tgt = this.nodeMap[edge.target];
      if (!src || !tgt) return;

      const x1 = src.x + src.width;
      const y1 = src.y + src.height / 2;
      const x2 = tgt.x;
      const y2 = tgt.y + tgt.height / 2;

      const dx = (x2 - x1) / 2;
      const pathD = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

      const strokeColor = tgt.type === 'dataset' ? '#38BDF8' : (tgt.type === 'experiment' ? '#10B981' : '#8B5CF6');
      const markerId = tgt.type === 'dataset' ? 'arrow-dataset' : (tgt.type === 'experiment' ? 'arrow-experiment' : 'arrow-default');

      html += `<path d="${pathD}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-opacity="0.75" marker-end="url(#${markerId})" />`;

      // Edge label chip at midpoint
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;
      html += `
        <rect x="${mx - 38}" y="${my - 8}" width="76" height="16" rx="3" fill="#070A12" stroke="#1E293B" />
        <text x="${mx}" y="${my + 3}" fill="#94A3B8" font-size="9" text-anchor="middle" font-family="monospace">${edge.label || edge.relation_type}</text>
      `;
    });

    // Draw Nodes
    this.data.nodes.forEach(node => {
      let bg = '#131A2B';
      let border = '#1E293B';
      let iconColor = '#94A3B8';
      let typeLabel = node.type.toUpperCase();

      if (node.type === 'dataset') {
        border = '#0284C7';
        iconColor = '#38BDF8';
        typeLabel = `DATASET v${node.version || 1}`;
      } else if (node.type === 'experiment') {
        border = '#059669';
        iconColor = '#10B981';
        typeLabel = `EXP • ${node.stage}`;
      } else if (node.type === 'candidate_set') {
        border = '#7C3AED';
        iconColor = '#A78BFA';
        typeLabel = 'CANDIDATES';
      }

      html += `
        <g class="prov-node" data-id="${node.id}" transform="translate(${node.x}, ${node.y})" style="cursor: pointer;">
          <rect width="${node.width}" height="${node.height}" rx="8" fill="${bg}" stroke="${border}" stroke-width="2" />
          <rect x="8" y="8" width="6" height="6" rx="3" fill="${iconColor}" />
          <text x="20" y="14" fill="${iconColor}" font-size="9.5" font-weight="700" font-family="system-ui" letter-spacing="0.05em">${typeLabel}</text>
          
          <text x="12" y="36" fill="#F8FAFC" font-size="12" font-weight="600" font-family="system-ui">
            ${this.truncateText(node.label || node.title, 22)}
          </text>
          <text x="12" y="52" fill="#94A3B8" font-size="10.5" font-family="system-ui">
            ${this.truncateText(node.subtitle || node.title || '', 25)}
          </text>
          <text x="12" y="66" fill="#64748B" font-size="9" font-family="monospace">
            ${(node.created_at || '').substring(0, 10)}
          </text>
        </g>
      `;
    });

    this.g.innerHTML = html;

    // Attach click listeners to nodes
    this.g.querySelectorAll('.prov-node').forEach(elem => {
      elem.addEventListener('click', (e) => {
        const id = elem.getAttribute('data-id');
        const node = this.data.nodes.find(n => n.id === id);
        if (node && this.onNodeClick) {
          this.onNodeClick(node);
        }
      });
    });
  },

  truncateText(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
  },

  updateTransform() {
    if (this.g) {
      this.g.setAttribute('transform', `translate(${this.transform.x}, ${this.transform.y}) scale(${this.transform.k})`);
    }
  },

  bindEvents() {
    const zoomIn = document.getElementById('prov-zoom-in');
    const zoomOut = document.getElementById('prov-zoom-out');
    const resetBtn = document.getElementById('prov-reset');

    if (zoomIn) zoomIn.addEventListener('click', () => {
      this.transform.k = Math.min(2.5, this.transform.k * 1.2);
      this.updateTransform();
    });

    if (zoomOut) zoomOut.addEventListener('click', () => {
      this.transform.k = Math.max(0.4, this.transform.k / 1.2);
      this.updateTransform();
    });

    if (resetBtn) resetBtn.addEventListener('click', () => {
      this.transform = { x: 40, y: 40, k: 0.95 };
      this.updateTransform();
    });

    // Pan via mouse drag
    this.svg.addEventListener('mousedown', (e) => {
      if (e.target.closest('.prov-node')) return;
      this.isDragging = true;
      this.dragStart = { x: e.clientX - this.transform.x, y: e.clientY - this.transform.y };
      this.svg.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.isDragging) return;
      this.transform.x = e.clientX - this.dragStart.x;
      this.transform.y = e.clientY - this.dragStart.y;
      this.updateTransform();
    });

    window.addEventListener('mouseup', () => {
      if (this.isDragging) {
        this.isDragging = false;
        this.svg.style.cursor = 'grab';
      }
    });

    // Zoom on wheel
    this.svg.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      this.transform.k = Math.max(0.3, Math.min(2.5, this.transform.k * zoomFactor));
      this.updateTransform();
    });
  }
};
