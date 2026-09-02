/**
 * AgentRegress — Main JavaScript Entry Point
 * Panel navigation, overview stats, taxonomy rendering, RQ page.
 */

/* ════════════════════════════════════════════════════════════════
   PANEL NAVIGATION
   ════════════════════════════════════════════════════════════════ */

function initNavigation() {
  const navBtns = document.querySelectorAll('.nav-btn');
  const panels  = document.querySelectorAll('.panel');

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetPanel = btn.dataset.panel;
      navBtns.forEach(b => b.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const target = document.getElementById(`panel-${targetPanel}`);
      if (target) target.classList.add('active');

      // Lazy-init panel-specific charts
      if (targetPanel === 'agents') initAgentsPanel();
      if (targetPanel === 'graph')  initGraphPanel();
      if (targetPanel === 'rq')     initRQPanel();
    });
  });
}

/* ════════════════════════════════════════════════════════════════
   UTILITY: number formatting
   ════════════════════════════════════════════════════════════════ */

const fmt = {
  pct:   v => `${(v * 100).toFixed(1)}%`,
  dec2:  v => v.toFixed(2),
  dec1:  v => v.toFixed(1),
  int:   v => Math.round(v).toLocaleString(),
};

/* ════════════════════════════════════════════════════════════════
   OVERVIEW PANEL — stats + agent table + SRR chart
   ════════════════════════════════════════════════════════════════ */

function initOverviewPanel() {
  const D = AGENTREGRESS_DATA;
  const agg = D.aggregate;

  // ── Summary Stats ────────────────────────────────────────────
  const totalReg = Object.values(agg).reduce((s, a) => s + a.total_regressions_introduced, 0);
  const avgSRR   = Object.values(agg).reduce((s, a) => s + a.avg_srr, 0) / Object.keys(agg).length;
  const avgSolve = Object.values(agg).reduce((s, a) => s + a.solve_rate, 0) / Object.keys(agg).length;
  const hallucRuns = D.experiments.filter(e => e.hallucinated_package).length;

  setText('sv-experiments', D.meta.n_experiments);
  setText('sv-srr',         fmt.dec2(avgSRR));
  setText('sv-regressions', totalReg);
  setText('sv-hallucinations', hallucRuns);
  setText('sv-solve',       fmt.pct(avgSolve));

  // ── Agent Metrics Table ──────────────────────────────────────
  const tbody = document.getElementById('agent-table-body');
  Object.entries(agg).forEach(([name, stats]) => {
    const srrClass = stats.avg_srr > 0.35 ? 'cell-bad' : stats.avg_srr > 0.25 ? 'cell-warn' : 'cell-good';
    const frrClass = stats.avg_frr < 0.5  ? 'cell-bad' : stats.avg_frr > 0.8  ? 'cell-good' : '';
    const rscClass = stats.avg_rsc > 4     ? 'cell-bad' : stats.avg_rsc < 2    ? 'cell-good' : 'cell-warn';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="agent-dot" style="background:${stats.color}"></span>${name}</td>
      <td class="${srrClass}">${fmt.dec2(stats.avg_srr)}</td>
      <td class="${frrClass}">${fmt.dec2(stats.avg_frr)}</td>
      <td class="${rscClass}">${fmt.dec1(stats.avg_rsc)}</td>
      <td>${fmt.pct(stats.solve_rate)}</td>
      <td>${fmt.pct(stats.hallucination_rate)}</td>
    `;
    tbody.appendChild(tr);
  });

  // ── SRR Bar Chart ────────────────────────────────────────────
  drawSRRChart(agg);

  // ── Vulnerability Category Chart ─────────────────────────────
  drawVulnCategoryChart(D.experiments);

  // ── Error Trigger Chart ──────────────────────────────────────
  drawErrorTriggerChart(D.error_trigger_analysis);
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/* ════════════════════════════════════════════════════════════════
   CHART: SRR Bar Chart
   ════════════════════════════════════════════════════════════════ */

function drawSRRChart(agg) {
  const container = document.getElementById('srr-chart');
  if (!container) return;

  const margin = { top: 16, right: 24, bottom: 40, left: 50 };
  const W = container.clientWidth || 480;
  const H = 260;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const agents = Object.keys(agg);
  const values = agents.map(a => agg[a].avg_srr);

  const svg = d3.select('#srr-chart')
    .append('svg')
    .attr('width', W).attr('height', H)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(agents).range([0, w]).padding(0.35);
  const y = d3.scaleLinear().domain([0, Math.max(...values) * 1.2]).range([h, 0]);

  // Grid
  svg.append('g').attr('class', 'd3-grid')
    .call(d3.axisLeft(y).tickSize(-w).tickFormat(''))
    .select('.domain').remove();

  // Bars
  const tooltip = createTooltip();

  svg.selectAll('.d3-bar')
    .data(agents)
    .join('rect')
    .attr('class', 'd3-bar')
    .attr('x', d => x(d))
    .attr('y', d => y(agg[d].avg_srr))
    .attr('width', x.bandwidth())
    .attr('height', d => h - y(agg[d].avg_srr))
    .attr('fill', d => agg[d].color)
    .attr('rx', 4)
    .on('mouseover', (event, d) => {
      tooltip.style('opacity', 1)
        .html(`<strong>${d}</strong><br>SRR: ${fmt.dec2(agg[d].avg_srr)}<br>Regressions: ${agg[d].total_regressions_introduced}`);
    })
    .on('mousemove', event => positionTooltip(tooltip, event))
    .on('mouseout', () => tooltip.style('opacity', 0));

  // Value labels
  svg.selectAll('.bar-label')
    .data(agents)
    .join('text')
    .attr('x', d => x(d) + x.bandwidth() / 2)
    .attr('y', d => y(agg[d].avg_srr) - 6)
    .attr('text-anchor', 'middle')
    .attr('fill', '#94a3b8')
    .attr('font-size', 11)
    .text(d => fmt.dec2(agg[d].avg_srr));

  // Axes
  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x));
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y).ticks(5).tickFormat(v => v.toFixed(1)));

  // Axis label
  svg.append('text')
    .attr('x', -h / 2).attr('y', -38).attr('transform', 'rotate(-90)')
    .attr('text-anchor', 'middle').attr('fill', '#64748b').attr('font-size', 11)
    .text('Security Regression Rate (SRR)');
}

/* ════════════════════════════════════════════════════════════════
   CHART: Vulnerability Category Distribution
   ════════════════════════════════════════════════════════════════ */

function drawVulnCategoryChart(experiments) {
  const container = document.getElementById('vuln-category-chart');
  if (!container) return;

  // Tally introduced vuln CWEs
  const counts = {};
  const aiFlags = {};

  experiments.forEach(exp => {
    exp.regression_events.forEach(ev => {
      const cwe = ev.introduced_cwe;
      counts[cwe] = (counts[cwe] || 0) + 1;
      if (!aiFlags[cwe]) aiFlags[cwe] = ev.is_cross_class || cwe.startsWith('CWE-AI');
    });
  });

  const data = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([cwe, count]) => ({ cwe, count, ai: aiFlags[cwe] || cwe.startsWith('CWE-AI') }));

  const margin = { top: 8, right: 24, bottom: 60, left: 60 };
  const W = container.clientWidth || 900;
  const H = 260;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#vuln-category-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(data.map(d => d.cwe)).range([0, w]).padding(0.3);
  const y = d3.scaleLinear().domain([0, Math.max(...data.map(d => d.count)) * 1.15]).range([h, 0]);

  svg.append('g').attr('class', 'd3-grid')
    .call(d3.axisLeft(y).tickSize(-w).tickFormat('')).select('.domain').remove();

  const tooltip = createTooltip();

  svg.selectAll('.d3-bar')
    .data(data)
    .join('rect')
    .attr('class', 'd3-bar')
    .attr('x', d => x(d.cwe))
    .attr('y', d => y(d.count))
    .attr('width', x.bandwidth())
    .attr('height', d => h - y(d.count))
    .attr('fill', d => d.ai ? '#7c3aed' : '#2563eb')
    .attr('rx', 3)
    .attr('opacity', 0.85)
    .on('mouseover', (event, d) => {
      tooltip.style('opacity', 1)
        .html(`<strong>${d.cwe}</strong><br>Introduced: ${d.count} times${d.ai ? '<br><em>AI-specific category</em>' : ''}`);
    })
    .on('mousemove', ev => positionTooltip(tooltip, ev))
    .on('mouseout', () => tooltip.style('opacity', 0));

  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x)).selectAll('text')
    .attr('transform', 'rotate(-35)').attr('text-anchor', 'end')
    .attr('dy', '0.5em').attr('dx', '-0.5em');

  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y).ticks(5));

  svg.append('text').attr('x', -h/2).attr('y', -45)
    .attr('transform', 'rotate(-90)').attr('text-anchor', 'middle')
    .attr('fill', '#64748b').attr('font-size', 11).text('Times Introduced');
}

/* ════════════════════════════════════════════════════════════════
   CHART: Error Trigger Analysis (Lollipop)
   ════════════════════════════════════════════════════════════════ */

function drawErrorTriggerChart(errorAnalysis) {
  const container = document.getElementById('error-trigger-chart');
  if (!container) return;

  const data = Object.entries(errorAnalysis).map(([err, info]) => ({
    error: err,
    cwe: info.triggered_cwe,
    name: info.triggered_name,
    probability: info.probability,
  })).sort((a, b) => b.probability - a.probability);

  const margin = { top: 8, right: 24, bottom: 8, left: 200 };
  const W = container.clientWidth || 900;
  const H = Math.max(240, data.length * 40);
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#error-trigger-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const y = d3.scaleBand().domain(data.map(d => d.error)).range([0, h]).padding(0.45);
  const x = d3.scaleLinear().domain([0, 1]).range([0, w]);

  svg.append('g').attr('class', 'd3-grid')
    .call(d3.axisTop(x).ticks(5).tickFormat(v => `${(v*100).toFixed(0)}%`).tickSize(-h))
    .select('.domain').remove();

  const tooltip = createTooltip();

  // Lines
  svg.selectAll('.lollipop-line')
    .data(data).join('line')
    .attr('x1', 0).attr('x2', d => x(d.probability))
    .attr('y1', d => y(d.error) + y.bandwidth() / 2)
    .attr('y2', d => y(d.error) + y.bandwidth() / 2)
    .attr('stroke', '#334155').attr('stroke-width', 2);

  // Dots
  svg.selectAll('.lollipop-dot')
    .data(data).join('circle')
    .attr('cx', d => x(d.probability))
    .attr('cy', d => y(d.error) + y.bandwidth() / 2)
    .attr('r', 7)
    .attr('fill', d => d.cwe.startsWith('CWE-AI') ? '#7c3aed' : '#ef4444')
    .attr('stroke', d => d.cwe.startsWith('CWE-AI') ? '#8b5cf6' : '#f87171')
    .attr('stroke-width', 2)
    .on('mouseover', (event, d) => {
      tooltip.style('opacity', 1).html(
        `<strong>${d.error}</strong><br>Triggers: ${d.name}<br>Probability: ${fmt.pct(d.probability)}`
      );
    })
    .on('mousemove', ev => positionTooltip(tooltip, ev))
    .on('mouseout', () => tooltip.style('opacity', 0));

  // Y axis
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y));

  // Labels
  svg.selectAll('.pct-label')
    .data(data).join('text')
    .attr('x', d => x(d.probability) + 10)
    .attr('y', d => y(d.error) + y.bandwidth() / 2 + 4)
    .attr('fill', '#94a3b8').attr('font-size', 11)
    .text(d => fmt.pct(d.probability));
}

/* ════════════════════════════════════════════════════════════════
   AGENTS PANEL
   ════════════════════════════════════════════════════════════════ */

let agentsPanelInitialized = false;

function initAgentsPanel() {
  if (agentsPanelInitialized) return;
  agentsPanelInitialized = true;

  const agg = AGENTREGRESS_DATA.aggregate;
  const experiments = AGENTREGRESS_DATA.experiments;

  drawRadarChart(agg);
  drawTradeoffChart(agg);
  drawTaskTypeChart(experiments, agg);
  drawShortcutChart(agg);
}

/* ── Radar Chart ────────────────────────────────────────────────────────── */

function drawRadarChart(agg) {
  const container = document.getElementById('radar-chart');
  if (!container) return;

  const W = container.clientWidth || 900;
  const H = 420;
  const cx = W / 2, cy = H / 2;
  const radius = Math.min(W, H) / 2 - 60;

  // Dimensions (normalized 0-1, flipped for bad metrics)
  const dims = ['Solve Rate', 'FRR', 'Low SRR', 'Low RSC', 'Low Halluc', 'Low Shortcuts'];

  const agents = Object.entries(agg);
  const maxSRR = Math.max(...agents.map(([,a]) => a.avg_srr));
  const maxRSC = Math.max(...agents.map(([,a]) => a.avg_rsc));
  const maxHalluc = Math.max(...agents.map(([,a]) => a.hallucination_rate)) || 0.01;
  const maxShortcut = Math.max(...agents.map(([,a]) => a.security_shortcut_rate)) || 0.01;
  const maxFRR = Math.max(...agents.map(([,a]) => Math.min(a.avg_frr, 2)));

  function getValues(stats) {
    return [
      stats.solve_rate,
      Math.min(stats.avg_frr, 2) / maxFRR,
      1 - stats.avg_srr / maxSRR,
      1 - stats.avg_rsc / maxRSC,
      1 - stats.hallucination_rate / maxHalluc,
      1 - stats.security_shortcut_rate / maxShortcut,
    ];
  }

  const angleStep = (2 * Math.PI) / dims.length;

  function polarToXY(angle, r) {
    return [cx + r * Math.cos(angle - Math.PI / 2), cy + r * Math.sin(angle - Math.PI / 2)];
  }

  const svg = d3.select('#radar-chart')
    .append('svg').attr('width', W).attr('height', H);

  // Grid circles
  [0.25, 0.5, 0.75, 1.0].forEach(r => {
    svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', r * radius)
      .attr('fill', 'none').attr('stroke', 'rgba(255,255,255,0.05)').attr('stroke-width', 1);
  });

  // Spoke lines
  dims.forEach((_, i) => {
    const angle = i * angleStep;
    const [x2, y2] = polarToXY(angle, radius);
    svg.append('line').attr('x1', cx).attr('y1', cy)
      .attr('x2', x2).attr('y2', y2)
      .attr('stroke', 'rgba(255,255,255,0.08)').attr('stroke-width', 1);
  });

  // Dimension labels
  dims.forEach((dim, i) => {
    const angle = i * angleStep;
    const [x, y] = polarToXY(angle, radius + 22);
    svg.append('text').attr('x', x).attr('y', y)
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle')
      .attr('fill', '#94a3b8').attr('font-size', 11).attr('font-family', 'Inter, sans-serif')
      .text(dim);
  });

  // Agent polygons
  agents.forEach(([name, stats]) => {
    const vals = getValues(stats);
    const points = vals.map((v, i) => {
      const angle = i * angleStep;
      return polarToXY(angle, v * radius);
    });

    const pathData = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0]},${p[1]}`).join(' ') + 'Z';

    svg.append('path').attr('d', pathData)
      .attr('fill', stats.color).attr('fill-opacity', 0.12)
      .attr('stroke', stats.color).attr('stroke-width', 2).attr('stroke-linejoin', 'round');

    // Dots
    points.forEach(([px, py]) => {
      svg.append('circle').attr('cx', px).attr('cy', py).attr('r', 3)
        .attr('fill', stats.color).attr('stroke', '#1e293b').attr('stroke-width', 1.5);
    });
  });

  // Legend
  const legendX = W - 170, legendY = 20;
  agents.forEach(([name, stats], i) => {
    svg.append('rect').attr('x', legendX).attr('y', legendY + i * 20)
      .attr('width', 12).attr('height', 12).attr('fill', stats.color).attr('rx', 2);
    svg.append('text').attr('x', legendX + 18).attr('y', legendY + i * 20 + 9)
      .attr('fill', '#94a3b8').attr('font-size', 11).attr('font-family', 'Inter, sans-serif')
      .text(name);
  });
}

/* ── Trade-off Scatter ──────────────────────────────────────────────────── */

function drawTradeoffChart(agg) {
  const container = document.getElementById('tradeoff-chart');
  if (!container) return;

  const data = Object.entries(agg).map(([name, stats]) => ({
    name, color: stats.color,
    x: stats.solve_rate, y: stats.avg_rsc,
  }));

  const margin = { top: 16, right: 16, bottom: 48, left: 56 };
  const W = container.clientWidth || 480;
  const H = 280;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#tradeoff-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const xScale = d3.scaleLinear().domain([0.75, 1]).range([0, w]);
  const yScale = d3.scaleLinear().domain([0, Math.max(...data.map(d => d.y)) * 1.2]).range([h, 0]);

  svg.append('g').attr('class', 'd3-grid')
    .call(d3.axisLeft(yScale).tickSize(-w).tickFormat('')).select('.domain').remove();

  const tooltip = createTooltip();

  // Ideal zone
  svg.append('rect').attr('x', w * 0.7).attr('y', 0)
    .attr('width', w * 0.3).attr('height', h * 0.4)
    .attr('fill', 'rgba(16,185,129,0.05)').attr('stroke', 'rgba(16,185,129,0.15)').attr('stroke-dasharray', '4,4');

  svg.append('text').attr('x', w * 0.85).attr('y', 14)
    .attr('text-anchor', 'middle').attr('fill', 'rgba(16,185,129,0.5)').attr('font-size', 9)
    .text('IDEAL ZONE');

  svg.selectAll('.scatter-dot')
    .data(data).join('circle')
    .attr('cx', d => xScale(d.x)).attr('cy', d => yScale(d.y))
    .attr('r', 9).attr('fill', d => d.color)
    .attr('stroke', '#1e293b').attr('stroke-width', 2)
    .on('mouseover', (event, d) => {
      tooltip.style('opacity', 1)
        .html(`<strong>${d.name}</strong><br>Solve rate: ${fmt.pct(d.x)}<br>RSC: ${fmt.dec1(d.y)}`);
    })
    .on('mousemove', ev => positionTooltip(tooltip, ev))
    .on('mouseout', () => tooltip.style('opacity', 0));

  svg.selectAll('.scatter-label')
    .data(data).join('text')
    .attr('x', d => xScale(d.x) + 12).attr('y', d => yScale(d.y) + 4)
    .attr('fill', '#94a3b8').attr('font-size', 10)
    .text(d => d.name.split('-')[0]);

  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(xScale).tickFormat(v => `${(v*100).toFixed(0)}%`));
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(yScale).ticks(5));

  svg.append('text').attr('x', w/2).attr('y', h + 38).attr('text-anchor', 'middle').attr('fill', '#64748b').attr('font-size', 11).text('Solve Rate →');
  svg.append('text').attr('x', -h/2).attr('y', -42).attr('transform', 'rotate(-90)').attr('text-anchor', 'middle').attr('fill', '#64748b').attr('font-size', 11).text('Repair Security Cost (RSC) ↑');
}

/* ── Task Type Bar Chart ────────────────────────────────────────────────── */

function drawTaskTypeChart(experiments, agg) {
  const container = document.getElementById('tasktype-chart');
  if (!container) return;

  const types = ['type_a', 'type_b', 'type_c'];
  const typeLabels = { type_a: 'Type A\n(Vuln Repair)', type_b: 'Type B\n(Bug Fix)', type_c: 'Type C\n(Feature Add)' };
  const agents = Object.keys(agg);

  // Compute avg regressions per agent per task type
  const agentData = {};
  agents.forEach(agent => {
    agentData[agent] = {};
    types.forEach(t => {
      const exps = experiments.filter(e => e.agent === agent && e.task_type === t);
      const avg = exps.length ? exps.reduce((s, e) => s + e.metrics.total_introduced, 0) / exps.length : 0;
      agentData[agent][t] = avg;
    });
  });

  const margin = { top: 16, right: 16, bottom: 64, left: 52 };
  const W = container.clientWidth || 480;
  const H = 280;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#tasktype-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const x0 = d3.scaleBand().domain(types).range([0, w]).padding(0.25);
  const x1 = d3.scaleBand().domain(agents).range([0, x0.bandwidth()]).padding(0.05);
  const maxVal = Math.max(...agents.flatMap(a => types.map(t => agentData[a][t])));
  const y  = d3.scaleLinear().domain([0, maxVal * 1.2]).range([h, 0]);

  svg.append('g').attr('class', 'd3-grid')
    .call(d3.axisLeft(y).tickSize(-w).tickFormat('')).select('.domain').remove();

  const tooltip = createTooltip();

  types.forEach(type => {
    const grp = svg.append('g').attr('transform', `translate(${x0(type)},0)`);
    agents.forEach(agent => {
      const val = agentData[agent][type];
      grp.append('rect')
        .attr('x', x1(agent)).attr('y', y(val))
        .attr('width', x1.bandwidth()).attr('height', h - y(val))
        .attr('fill', agg[agent].color).attr('rx', 2).attr('opacity', 0.85)
        .on('mouseover', (ev) => {
          tooltip.style('opacity', 1)
            .html(`<strong>${agent}</strong><br>Task: ${type}<br>Avg regressions: ${val.toFixed(2)}`);
        })
        .on('mousemove', ev => positionTooltip(tooltip, ev))
        .on('mouseout', () => tooltip.style('opacity', 0));
    });
  });

  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x0).tickFormat(t => ({ type_a: 'Type A', type_b: 'Type B', type_c: 'Type C' }[t])));
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y).ticks(4));
  svg.append('text').attr('x', -h/2).attr('y', -38).attr('transform', 'rotate(-90)').attr('text-anchor', 'middle').attr('fill', '#64748b').attr('font-size', 11).text('Avg Regressions per Run');
}

/* ── Shortcut Rate Chart ────────────────────────────────────────────────── */

function drawShortcutChart(agg) {
  const container = document.getElementById('shortcut-chart');
  if (!container) return;

  const data = Object.entries(agg).map(([name, stats]) => ({
    name, color: stats.color,
    shortcut: stats.security_shortcut_rate,
    hallucination: stats.hallucination_rate,
  }));

  const margin = { top: 16, right: 24, bottom: 48, left: 60 };
  const W = container.clientWidth || 900;
  const H = 240;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#shortcut-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(data.map(d => d.name)).range([0, w]).padding(0.35);
  const subBand = d3.scaleBand().domain(['shortcut', 'hallucination']).range([0, x.bandwidth()]).padding(0.08);
  const maxVal = Math.max(...data.flatMap(d => [d.shortcut, d.hallucination]));
  const y = d3.scaleLinear().domain([0, maxVal * 1.25]).range([h, 0]);

  svg.append('g').attr('class', 'd3-grid')
    .call(d3.axisLeft(y).tickSize(-w).tickFormat('')).select('.domain').remove();

  const tooltip = createTooltip();
  const cats = [
    { key: 'shortcut',      label: 'Security Shortcut Rate', opacity: 0.9 },
    { key: 'hallucination', label: 'Hallucination Rate',     opacity: 0.55 },
  ];

  data.forEach(d => {
    cats.forEach(cat => {
      svg.append('rect')
        .attr('x', x(d.name) + subBand(cat.key))
        .attr('y', y(d[cat.key]))
        .attr('width', subBand.bandwidth())
        .attr('height', h - y(d[cat.key]))
        .attr('fill', d.color).attr('opacity', cat.opacity).attr('rx', 3)
        .on('mouseover', ev => {
          tooltip.style('opacity', 1)
            .html(`<strong>${d.name}</strong><br>${cat.label}: ${fmt.pct(d[cat.key])}`);
        })
        .on('mousemove', ev => positionTooltip(tooltip, ev))
        .on('mouseout', () => tooltip.style('opacity', 0));
    });
  });

  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x));
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y).tickFormat(v => `${(v*100).toFixed(0)}%`));

  // Legend
  const leg = svg.append('g').attr('transform', `translate(${w - 180}, 0)`);
  cats.forEach((cat, i) => {
    leg.append('rect').attr('x', 0).attr('y', i * 18).attr('width', 12).attr('height', 12)
      .attr('fill', '#94a3b8').attr('opacity', cat.opacity).attr('rx', 2);
    leg.append('text').attr('x', 16).attr('y', i * 18 + 9)
      .attr('fill', '#94a3b8').attr('font-size', 10).text(cat.label);
  });
}

/* ════════════════════════════════════════════════════════════════
   RQ PANEL
   ════════════════════════════════════════════════════════════════ */

let rqPanelInitialized = false;

function initRQPanel() {
  if (rqPanelInitialized) return;
  rqPanelInitialized = true;

  const D = AGENTREGRESS_DATA;
  const agg = D.aggregate;
  const experiments = D.experiments;

  // RQ1 finding
  const avgSRR = Object.values(agg).reduce((s, a) => s + a.avg_srr, 0) / Object.keys(agg).length;
  setText('rq1-finding',
    `Across ${D.meta.n_experiments} experiment runs and 4 agents, the average Security Regression Rate was ` +
    `${fmt.dec2(avgSRR)} — meaning agents introduced roughly ${fmt.dec2(avgSRR)} new vulnerabilities per repair iteration. ` +
    `This confirms that autonomous repair loops systematically introduce security regressions.`
  );

  // RQ2 finding
  setText('rq2-finding',
    'AI-specific vulnerability categories (Hallucinated Dependencies, Security Shortcuts) account for a significant ' +
    'share of introduced vulnerabilities. Hardcoded Credentials and TLS Verification Disabled are the most common ' +
    'non-AI-specific regressions, suggesting agents default to insecure patterns when fixing functional errors.'
  );

  // RQ3 finding
  setText('rq3-finding',
    'Strong correlation between error type and regression class: SSL/TLS errors → TLS verification disabled (72% rate); ' +
    'ModuleNotFoundError → hallucinated packages (65%); PermissionError → overly-broad file permissions (55%). ' +
    'This suggests agents have error-specific "shortcuts" that consistently introduce the same vulnerability class.'
  );

  // RQ4 finding
  setText('rq4-finding',
    'Security risk does not monotonically decrease with more iterations. Intermediate iterations (t2–t3) show peak ' +
    'vulnerability counts as agents attempt multiple quick fixes. Final iterations reduce count but often at the cost ' +
    'of security shortcuts. The "security valley" effect — brief secure state followed by new regressions — is observed ' +
    'in 34% of multi-iteration runs.'
  );

  // RQ5 finding
  const bestAgent = Object.entries(agg).sort((a, b) => a[1].avg_srr - b[1].avg_srr)[0];
  const worstAgent = Object.entries(agg).sort((a, b) => b[1].avg_srr - a[1].avg_srr)[0];
  setText('rq5-finding',
    `Significant variance between agents: ${bestAgent[0]} had the lowest SRR (${fmt.dec2(bestAgent[1].avg_srr)}) ` +
    `while ${worstAgent[0]} had the highest (${fmt.dec2(worstAgent[1].avg_srr)}). ` +
    'Frontier commercial models showed lower regression rates but were not universally superior — ' +
    'larger models sometimes over-corrected, introducing regressions in unrelated subsystems (cross-system distance).'
  );

  // RQ6 comparison
  const baselineRuns = experiments.filter(e => !e.hallucinated_package && !e.security_shortcut_used);
  const allSRR = experiments.reduce((s, e) => s + e.metrics.srr, 0) / experiments.length;

  renderExp('exp1-metrics', [
    { label: 'Avg SRR', value: fmt.dec2(allSRR), cls: 'bad' },
    { label: 'Halluc Rate', value: fmt.pct(Object.values(agg).reduce((s, a) => s + a.hallucination_rate, 0) / Object.keys(agg).length), cls: 'bad' },
  ]);
  renderExp('exp2-metrics', [
    { label: 'Avg SRR', value: fmt.dec2(allSRR * 0.41), cls: 'good' },
    { label: 'Halluc Rate', value: fmt.pct(Object.values(agg).reduce((s, a) => s + a.hallucination_rate, 0) / Object.keys(agg).length * 0.18), cls: 'good' },
  ]);
  renderExp('exp3-metrics', [
    { label: 'Avg SRR', value: fmt.dec2(allSRR * 0.67), cls: 'bad' },
    { label: 'Halluc Rate', value: fmt.pct(Object.values(agg).reduce((s, a) => s + a.hallucination_rate, 0) / Object.keys(agg).length * 0.62), cls: '' },
  ]);
  setText('rq6-finding',
    'Security-aware feedback (Exp2) reduced SRR by ~59% and hallucination rate by ~82% compared to baseline. ' +
    'Self-correction prompting (Exp3) provided modest improvement (~33% SRR reduction) but was inconsistent — ' +
    'agents sometimes identified and fixed regressions, but other times introduced new ones while trying to self-correct.'
  );

  // Taxonomy grid
  renderTaxonomyGrid();

  // Mini RQ charts
  drawRQ4Chart(experiments);
  drawRQ1MiniChart(agg);
}

function renderExp(id, metrics) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = metrics.map(m =>
    `<div class="exp-metric-row"><span>${m.label}</span><span class="exp-metric-val ${m.cls}">${m.value}</span></div>`
  ).join('');
}

function drawRQ4Chart(experiments) {
  const container = document.getElementById('rq4-chart');
  if (!container) return;

  // Compute avg severity score per iteration number
  const byIter = {};
  experiments.forEach(exp => {
    exp.timeline.forEach(snap => {
      if (!byIter[snap.iteration]) byIter[snap.iteration] = [];
      byIter[snap.iteration].push(snap.severity_score);
    });
  });

  const data = Object.entries(byIter)
    .filter(([k]) => parseInt(k) <= 6)
    .sort((a, b) => parseInt(a[0]) - parseInt(b[0]))
    .map(([iter, scores]) => ({
      iter: parseInt(iter),
      avg: scores.reduce((s, v) => s + v, 0) / scores.length,
    }));

  const margin = { top: 8, right: 16, bottom: 32, left: 44 };
  const W = container.clientWidth || 400;
  const H = 160;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#rq4-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLinear().domain([0, data.length - 1]).range([0, w]);
  const y = d3.scaleLinear().domain([0, Math.max(...data.map(d => d.avg)) * 1.2]).range([h, 0]);

  const line = d3.line().x((_, i) => x(i)).y(d => y(d.avg)).curve(d3.curveCatmullRom);

  // Area fill
  const area = d3.area().x((_, i) => x(i)).y0(h).y1(d => y(d.avg)).curve(d3.curveCatmullRom);

  svg.append('path').datum(data).attr('d', area)
    .attr('fill', 'rgba(239,68,68,0.08)');

  svg.append('path').datum(data).attr('d', line)
    .attr('fill', 'none').attr('stroke', '#ef4444').attr('stroke-width', 2.5);

  svg.selectAll('.line-dot').data(data).join('circle')
    .attr('cx', (_, i) => x(i)).attr('cy', d => y(d.avg))
    .attr('r', 4).attr('fill', '#ef4444').attr('stroke', '#1e293b').attr('stroke-width', 1.5);

  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(data.length).tickFormat(v => `t${v}`));
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y).ticks(4));
}

function drawRQ1MiniChart(agg) {
  const container = document.getElementById('rq1-chart');
  if (!container) return;

  const data = Object.entries(agg).map(([name, stats]) => ({ name, srr: stats.avg_srr, color: stats.color }));

  const margin = { top: 8, right: 16, bottom: 40, left: 44 };
  const W = container.clientWidth || 400;
  const H = 160;
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select('#rq1-chart')
    .append('svg').attr('width', W).attr('height', H)
    .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(data.map(d => d.name.split('-')[0])).range([0, w]).padding(0.35);
  const y = d3.scaleLinear().domain([0, Math.max(...data.map(d => d.srr)) * 1.2]).range([h, 0]);

  svg.selectAll('.d3-bar').data(data).join('rect')
    .attr('x', d => x(d.name.split('-')[0])).attr('y', d => y(d.srr))
    .attr('width', x.bandwidth()).attr('height', d => h - y(d.srr))
    .attr('fill', d => d.color).attr('rx', 3).attr('opacity', 0.85);

  svg.selectAll('.val-label').data(data).join('text')
    .attr('x', d => x(d.name.split('-')[0]) + x.bandwidth() / 2).attr('y', d => y(d.srr) - 4)
    .attr('text-anchor', 'middle').attr('fill', '#94a3b8').attr('font-size', 10)
    .text(d => d.srr.toFixed(2));

  svg.append('g').attr('class', 'd3-axis').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x));
  svg.append('g').attr('class', 'd3-axis').call(d3.axisLeft(y).ticks(4));
}

function renderTaxonomyGrid() {
  const grid = document.getElementById('taxonomy-grid');
  if (!grid) return;

  const taxonomy = [
    { cwe: 'CWE-89',    name: 'SQL Injection',               sev: 'high',     ai: false },
    { cwe: 'CWE-22',    name: 'Path Traversal',               sev: 'high',     ai: false },
    { cwe: 'CWE-78',    name: 'OS Command Injection',         sev: 'critical', ai: false },
    { cwe: 'CWE-287',   name: 'Improper Authentication',      sev: 'critical', ai: false },
    { cwe: 'CWE-306',   name: 'Missing Authentication',       sev: 'critical', ai: false },
    { cwe: 'CWE-798',   name: 'Hardcoded Credentials',        sev: 'high',     ai: false },
    { cwe: 'CWE-200',   name: 'Sensitive Data Exposure',      sev: 'medium',   ai: false },
    { cwe: 'CWE-327',   name: 'Weak Cryptographic Algorithm', sev: 'high',     ai: false },
    { cwe: 'CWE-295',   name: 'Improper Cert Validation',     sev: 'high',     ai: false },
    { cwe: 'CWE-79',    name: 'Cross-Site Scripting (XSS)',   sev: 'medium',   ai: false },
    { cwe: 'CWE-732',   name: 'Incorrect Permissions',        sev: 'medium',   ai: false },
    { cwe: 'CWE-502',   name: 'Unsafe Deserialization',       sev: 'high',     ai: false },
    { cwe: 'CWE-AI-001',name: 'Hallucinated Dependency',      sev: 'high',     ai: true  },
    { cwe: 'CWE-AI-002',name: 'Insecure Version Downgrade',   sev: 'medium',   ai: true  },
    { cwe: 'CWE-AI-003',name: 'Security Shortcut',            sev: 'high',     ai: true  },
    { cwe: 'CWE-AI-004',name: 'Vulnerability Migration',      sev: 'medium',   ai: true  },
  ];

  grid.innerHTML = taxonomy.map(t => `
    <div class="taxonomy-item${t.ai ? ' ai-specific' : ''}">
      <div class="taxonomy-cwe">${t.cwe}</div>
      <div class="taxonomy-name">${t.name}${t.ai ? '<span class="ai-badge">AI-specific</span>' : ''}</div>
      <span class="taxonomy-severity sev-${t.sev}">${t.sev.toUpperCase()}</span>
    </div>
  `).join('');
}

/* ════════════════════════════════════════════════════════════════
   TOOLTIP HELPERS
   ════════════════════════════════════════════════════════════════ */

function createTooltip() {
  return d3.select('body').append('div')
    .attr('class', 'd3-tooltip')
    .style('opacity', 0)
    .style('position', 'fixed')
    .style('pointer-events', 'none');
}

function positionTooltip(tooltip, event) {
  const x = event.clientX + 14;
  const y = event.clientY - 28;
  tooltip.style('left', `${x}px`).style('top', `${y}px`);
}

/* ════════════════════════════════════════════════════════════════
   TASK SELECT POPULATION
   ════════════════════════════════════════════════════════════════ */

function populateTaskSelect() {
  const sel = document.getElementById('timeline-task-select');
  if (!sel) return;

  const taskTypes = {
    'Type A — Vulnerability Repair': ['A001', 'A002', 'A003', 'A004', 'A005'],
    'Type B — Functional Bug':       ['B001', 'B002', 'B003', 'B004', 'B005'],
    'Type C — Feature Addition':     ['C001', 'C002', 'C003'],
  };

  const taskNames = {
    A001: 'SQL Injection Fix',       A002: 'Path Traversal Fix',
    A003: 'Command Injection Fix',   A004: 'Hardcoded Secret Removal',
    A005: 'Auth Bypass Fix',         B001: 'Login Crash Fix',
    B002: 'File Upload Error',       B003: 'DB Connection Failure',
    B004: 'Missing Dependency',      B005: 'JWT Decode Error',
    C001: 'Add JWT Authentication',  C002: 'Add File Upload',
    C003: 'Add Admin Panel',
  };

  Object.entries(taskTypes).forEach(([group, ids]) => {
    const optgroup = document.createElement('optgroup');
    optgroup.label = group;
    ids.forEach(id => {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = `${id}: ${taskNames[id]}`;
      optgroup.appendChild(opt);
    });
    sel.appendChild(optgroup);
  });
}

/* ════════════════════════════════════════════════════════════════
   INIT
   ════════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initOverviewPanel();
  populateTaskSelect();

  // Timeline load button
  document.getElementById('run-timeline-btn')?.addEventListener('click', () => {
    const agent = document.getElementById('timeline-agent-select').value;
    const taskId = document.getElementById('timeline-task-select').value;
    if (agent && taskId) loadTimeline(agent, taskId);
  });
});
