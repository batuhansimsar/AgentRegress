/**
 * AgentRegress — Vulnerability Graph + Distance Chart
 * D3 force-directed graph showing CWE → CWE transition patterns.
 */

let graphPanelInitialized = false;

function initGraphPanel() {
  if (graphPanelInitialized) return;
  graphPanelInitialized = true;

  drawVulnGraph(AGENTREGRESS_DATA.vulnerability_graph);
  drawDistanceChart(AGENTREGRESS_DATA.experiments);
}

/* ════════════════════════════════════════════════════════════════
   FORCE-DIRECTED VULNERABILITY TRANSITION GRAPH
   ════════════════════════════════════════════════════════════════ */

function drawVulnGraph(graphData) {
  const container = document.getElementById('vuln-graph-svg');
  if (!container) return;

  const W = container.clientWidth || 1000;
  const H = 440;

  // Build nodes + links from graph data
  const nodeSet = new Set();
  const links = [];

  Object.entries(graphData).forEach(([src, targets]) => {
    nodeSet.add(src);
    Object.entries(targets).forEach(([dst, count]) => {
      nodeSet.add(dst);
      links.push({ source: src, target: dst, value: count });
    });
  });

  const AI_CWES = new Set(['CWE-AI-001', 'CWE-AI-002', 'CWE-AI-003', 'CWE-AI-004']);
  const CWE_NAMES = {
    'CWE-89':  'SQL Injection',
    'CWE-22':  'Path Traversal',
    'CWE-78':  'Cmd Injection',
    'CWE-287': 'Broken Auth',
    'CWE-306': 'Missing Auth',
    'CWE-798': 'Hardcoded\nSecret',
    'CWE-200': 'Info Disclosure',
    'CWE-327': 'Weak Crypto',
    'CWE-295': 'TLS Disabled',
    'CWE-79':  'XSS',
    'CWE-732': 'Bad Permissions',
    'CWE-502': 'Unsafe Deser.',
    'CWE-AI-001': 'Hallucinated\nDep.',
    'CWE-AI-002': 'Version\nDowngrade',
    'CWE-AI-003': 'Security\nShortcut',
    'CWE-AI-004': 'Vuln\nMigration',
  };

  const nodes = Array.from(nodeSet).map(id => ({
    id,
    name: CWE_NAMES[id] || id,
    ai: AI_CWES.has(id),
    degree: links.filter(l => l.source === id || l.target === id).length,
  }));

  const maxLinkValue = Math.max(...links.map(l => l.value));

  const svg = d3.select('#vuln-graph-svg')
    .append('svg').attr('width', W).attr('height', H)
    .style('background', 'transparent');

  // Arrow marker
  svg.append('defs').append('marker')
    .attr('id', 'arrow').attr('viewBox', '0 -4 8 8')
    .attr('refX', 18).attr('refY', 0)
    .attr('markerWidth', 6).attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-4L8,0L0,4')
    .attr('fill', '#475569');

  // Force simulation
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(d => 120 - d.value * 5))
    .force('charge', d3.forceManyBody().strength(-280))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(40));

  const tooltip = createTooltip();

  // Links
  const link = svg.append('g').selectAll('line')
    .data(links).join('line')
    .attr('stroke', '#334155')
    .attr('stroke-width', d => 1 + (d.value / maxLinkValue) * 5)
    .attr('stroke-opacity', 0.7)
    .attr('marker-end', 'url(#arrow)')
    .on('mouseover', (event, d) => {
      tooltip.style('opacity', 1)
        .html(`<strong>${d.source.id || d.source}</strong> → <strong>${d.target.id || d.target}</strong><br>Observed ${d.value} time${d.value !== 1 ? 's' : ''}`);
    })
    .on('mousemove', ev => positionTooltip(tooltip, ev))
    .on('mouseout', () => tooltip.style('opacity', 0));

  // Node groups
  const node = svg.append('g').selectAll('.node-group')
    .data(nodes).join('g')
    .attr('class', 'node-group')
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
      })
    );

  // Node circles
  node.append('circle')
    .attr('r', d => 12 + d.degree * 2.5)
    .attr('fill', d => d.ai ? 'rgba(124,58,237,0.3)' : 'rgba(37,99,235,0.2)')
    .attr('stroke', d => d.ai ? '#7c3aed' : '#2563eb')
    .attr('stroke-width', 2)
    .on('mouseover', (event, d) => {
      const outgoing = links.filter(l => (l.source.id || l.source) === d.id).length;
      const incoming = links.filter(l => (l.target.id || l.target) === d.id).length;
      tooltip.style('opacity', 1)
        .html(`<strong>${d.id}</strong><br>${d.name.replace('\n', ' ')}<br>Incoming: ${incoming} | Outgoing: ${outgoing}${d.ai ? '<br><em>AI-specific category</em>' : ''}`);
    })
    .on('mousemove', ev => positionTooltip(tooltip, ev))
    .on('mouseout', () => tooltip.style('opacity', 0));

  // Node labels (multi-line support)
  node.each(function(d) {
    const parts = d.name.split('\n');
    const grp = d3.select(this);
    parts.forEach((part, i) => {
      grp.append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('dy', `${(i - (parts.length - 1) / 2) * 12}px`)
        .attr('fill', '#cbd5e1')
        .attr('font-size', 9)
        .attr('font-family', 'Inter, sans-serif')
        .attr('font-weight', 500)
        .attr('pointer-events', 'none')
        .text(part);
    });
  });

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

/* ════════════════════════════════════════════════════════════════
   REGRESSION DISTANCE DISTRIBUTION
   ════════════════════════════════════════════════════════════════ */

function drawDistanceChart(experiments) {
  const container = document.getElementById('distance-chart');
  if (!container) return;

  const distanceCounts = { local: 0, file: 0, module: 0, cross: 0 };
  const distanceByAgent = {};

  experiments.forEach(exp => {
    if (!distanceByAgent[exp.agent]) {
      distanceByAgent[exp.agent] = { local: 0, file: 0, module: 0, cross: 0 };
    }
    exp.regression_events.forEach(ev => {
      const dist = ev.distance || 'module';
      distanceCounts[dist] = (distanceCounts[dist] || 0) + 1;
      distanceByAgent[exp.agent][dist] = (distanceByAgent[exp.agent][dist] || 0) + 1;
    });
  });

  const distLabels = {
    local:  '📍 Local\n(same function)',
    file:   '📄 File-Level\n(same file)',
    module: '📦 Module-Level\n(same component)',
    cross:  '⚡ Cross-System\n(diff. component)',
  };

  const distColors = {
    local:  '#10b981',
    file:   '#2563eb',
    module: '#f59e0b',
    cross:  '#dc2626',
  };

  const agents = Object.keys(distanceByAgent);
  const categories = ['local', 'file', 'module', 'cross'];

  const margin = { top: 16, right: 200, bottom: 64, left: 60 };
  const W = container.clientWidth || 900;
  const H = 260;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#distance-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const x0 = d3.scaleBand().domain(agents).range([0, w]).padding(0.25);
  const x1 = d3.scaleBand().domain(categories).range([0, x0.bandwidth()]).padding(0.05);
  const maxVal = Math.max(...agents.flatMap(a => categories.map(c => distanceByAgent[a][c] || 0)));
  const y = d3.scaleLinear().domain([0, maxVal * 1.2 || 10]).range([h, 0]);

  svg.append('g').attr('class', 'd3-grid')
    .call(d3.axisLeft(y).tickSize(-w).tickFormat('')).select('.domain').remove();

  const tooltip = createTooltip();

  agents.forEach(agent => {
    const grp = svg.append('g').attr('transform', `translate(${x0(agent)},0)`);
    categories.forEach(cat => {
      const val = distanceByAgent[agent][cat] || 0;
      grp.append('rect')
        .attr('x', x1(cat)).attr('y', y(val))
        .attr('width', x1.bandwidth()).attr('height', h - y(val))
        .attr('fill', distColors[cat]).attr('rx', 2).attr('opacity', 0.8)
        .on('mouseover', ev => {
          tooltip.style('opacity', 1)
            .html(`<strong>${agent}</strong><br>Distance: ${cat}<br>Count: ${val}`);
        })
        .on('mousemove', ev => positionTooltip(tooltip, ev))
        .on('mouseout', () => tooltip.style('opacity', 0));
    });
  });

  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x0).tickFormat(a => a.split('-')[0]));
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y).ticks(5));
  svg.append('text').attr('x', -h/2).attr('y', -42).attr('transform', 'rotate(-90)').attr('text-anchor', 'middle').attr('fill', '#64748b').attr('font-size', 11).text('Regression Count');

  // Legend
  const leg = svg.append('g').attr('transform', `translate(${w + 20}, 0)`);
  categories.forEach((cat, i) => {
    leg.append('rect').attr('x', 0).attr('y', i * 30).attr('width', 14).attr('height', 14)
      .attr('fill', distColors[cat]).attr('rx', 2);
    const lines = distLabels[cat].split('\n');
    lines.forEach((line, li) => {
      leg.append('text').attr('x', 20).attr('y', i * 30 + 9 + li * 11)
        .attr('fill', li === 0 ? '#e2e8f0' : '#64748b')
        .attr('font-size', li === 0 ? 11 : 9)
        .attr('font-family', 'Inter, sans-serif')
        .text(line);
    });
  });
}
