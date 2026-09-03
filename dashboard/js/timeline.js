/**
 * AgentRegress — Timeline Visualization
 * Whack-a-Mole timeline renderer + Regression Event Log
 */

/**
 * Load and render a specific experiment timeline.
 * @param {string} agentName - e.g., "GPT-4o"
 * @param {string} taskId    - e.g., "A001"
 */
function loadTimeline(agentName, taskId) {
  const experiment = AGENTREGRESS_DATA.experiments.find(
    e => e.agent === agentName && e.task_id === taskId
  );

  if (!experiment) {
    alert(`No experiment found for ${agentName} / ${taskId}`);
    return;
  }

  renderWAMTitle(experiment);
  renderWAMTimeline(experiment);
  renderMetricChips(experiment);
  renderRegressionLog(experiment);
}

/* ════════════════════════════════════════════════════════════════
   TITLE + STATUS BADGES
   ════════════════════════════════════════════════════════════════ */

function renderWAMTitle(exp) {
  const title = document.getElementById('wam-title');
  if (title) title.textContent = `${exp.agent} — ${exp.task_name}`;

  const solveBadge  = document.getElementById('wam-solve-badge');
  const secureBadge = document.getElementById('wam-secure-badge');

  if (solveBadge) {
    solveBadge.textContent = exp.task_solved ? '✓ Task Solved' : '✗ Task Unsolved';
    solveBadge.className = `status-badge ${exp.task_solved ? 'solved' : 'unsolved'}`;
  }

  if (secureBadge) {
    secureBadge.textContent = exp.final_secure ? '🔒 Final: Secure' : '⚠ Final: Insecure';
    secureBadge.className = `status-badge ${exp.final_secure ? 'secure' : 'insecure'}`;
  }
}

/* ════════════════════════════════════════════════════════════════
   WHACK-A-MOLE TIMELINE
   ════════════════════════════════════════════════════════════════ */

function renderWAMTimeline(exp) {
  const container = document.getElementById('timeline-vis');
  if (!container) return;

  const timeline = exp.timeline;

  // Build a set of "fixed CWEs per iteration" for status tracking
  const fixedByIter = {};
  timeline.forEach(snap => {
    fixedByIter[snap.iteration] = new Set(snap.fixed || []);
  });

  const wamEl = document.createElement('div');
  wamEl.className = 'wam-timeline';

  timeline.forEach((snap, idx) => {
    const step = document.createElement('div');
    step.className = 'wam-step';

    // All CWEs visible in this iteration
    const persistentCWEs = new Set(
      (idx === 0 ? [] : timeline[idx - 1].vulnerabilities.map(v => v.cwe))
        .filter(c => !fixedByIter[snap.iteration].has(c))
    );
    const introducedCWEs = new Set(snap.introduced || []);

    const inner = document.createElement('div');
    inner.className = 'wam-step-inner';
    inner.style.borderTopColor = idx === 0 ? '#475569' : (introducedCWEs.size > 0 ? '#dc2626' : '#10b981');

    const labelEl = document.createElement('div');
    labelEl.className = 'wam-step-label';
    labelEl.textContent = snap.label;

    const iterEl = document.createElement('div');
    iterEl.className = 'wam-step-iteration';
    iterEl.textContent = `t${snap.iteration}`;

    // Feedback badge
    let feedbackEl = '';
    if (snap.feedback) {
      feedbackEl = `<div style="font-size:0.65rem;color:#f59e0b;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);border-radius:4px;padding:3px 6px;margin-bottom:4px;">⚡ ${snap.feedback}</div>`;
    }

    // Vulnerability list
    const vulnListEl = document.createElement('div');
    vulnListEl.className = 'wam-vuln-list';

    // Show fixed vulns from previous iteration
    if (idx > 0 && fixedByIter[snap.iteration].size > 0) {
      fixedByIter[snap.iteration].forEach(cwe => {
        const item = document.createElement('div');
        item.className = 'wam-vuln-item status-fixed';
        item.innerHTML = `<span class="vuln-icon">✓</span><span>${shortCWEName(cwe)}</span>`;
        vulnListEl.appendChild(item);
      });
    }

    // Show current vulnerabilities
    snap.vulnerabilities.forEach(vuln => {
      const item = document.createElement('div');
      const isIntroduced = introducedCWEs.has(vuln.cwe);
      item.className = `wam-vuln-item ${isIntroduced ? 'status-introduced' : 'status-persistent'}`;
      const icon = isIntroduced ? '🔴' : '🟡';
      const prefix = isIntroduced ? 'NEW: ' : '';
      const sevLabel = vuln.severity ? ` [${vuln.severity}]` : '';
      item.innerHTML = `<span class="vuln-icon">${icon}</span><span>${prefix}${shortCWEName(vuln.cwe)}${sevLabel}</span>`;
      item.title = vuln.name || vuln.cwe;
      vulnListEl.appendChild(item);
    });

    if (snap.vulnerabilities.length === 0 && fixedByIter[snap.iteration].size === 0) {
      const item = document.createElement('div');
      item.style.cssText = 'font-size:0.7rem;color:#10b981;padding:6px 8px;background:rgba(16,185,129,0.06);border-radius:4px;';
      item.textContent = '🟢 No vulnerabilities';
      vulnListEl.appendChild(item);
    }

    const totalEl = document.createElement('div');
    totalEl.className = 'wam-step-total';
    const fixed = fixedByIter[snap.iteration].size;
    const introduced = introducedCWEs.size;
    totalEl.innerHTML = `Total: ${snap.total} vuln${snap.total !== 1 ? 's' : ''}` +
      (fixed > 0 ? ` | <span style="color:#10b981">-${fixed} fixed</span>` : '') +
      (introduced > 0 ? ` | <span style="color:#ef4444">+${introduced} new</span>` : '');

    inner.innerHTML = '';
    inner.appendChild(labelEl);
    inner.appendChild(iterEl);
    if (snap.feedback) {
      const fb = document.createElement('div');
      fb.style.cssText = 'font-size:0.65rem;color:#f59e0b;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);border-radius:4px;padding:3px 6px;margin-bottom:4px;';
      fb.textContent = `⚡ ${snap.feedback}`;
      inner.appendChild(fb);
    }
    inner.appendChild(vulnListEl);
    inner.appendChild(totalEl);

    step.appendChild(inner);
    wamEl.appendChild(step);
  });

  container.innerHTML = '';
  container.appendChild(wamEl);
}

function shortCWEName(cwe) {
  const map = {
    'CWE-89': 'SQL Injection',
    'CWE-22': 'Path Traversal',
    'CWE-78': 'Cmd Injection',
    'CWE-287': 'Broken Auth',
    'CWE-306': 'Missing Auth',
    'CWE-798': 'Hardcoded Secret',
    'CWE-200': 'Info Disclosure',
    'CWE-327': 'Weak Crypto',
    'CWE-295': 'TLS Disabled',
    'CWE-79': 'XSS',
    'CWE-732': 'Bad Permissions',
    'CWE-502': 'Unsafe Deser.',
    'AR-001': 'Hallucinated Dep.',
    'AR-002': 'Version Downgrade',
    'AR-003': 'Security Shortcut',
    'AR-004': 'Vuln Migration',
  };
  return map[cwe] || cwe;
}

/* ════════════════════════════════════════════════════════════════
   METRIC CHIPS
   ════════════════════════════════════════════════════════════════ */

function renderMetricChips(exp) {
  const row = document.getElementById('exp-metrics-row');
  if (row) row.style.display = 'grid';

  setValue('mcv-srr',   exp.metrics.srr.toFixed(3));
  setValue('mcv-frr',   exp.metrics.fix_to_regression_ratio.toFixed(2));
  setValue('mcv-rsc',   exp.metrics.repair_security_cost.toFixed(1));
  setValue('mcv-churn', exp.metrics.security_churn);

  // Color coding
  colorChip('mc-srr',   exp.metrics.srr > 0.4 ? 'bad' : exp.metrics.srr < 0.2 ? 'good' : 'warn');
  colorChip('mc-frr',   exp.metrics.fix_to_regression_ratio < 0.5 ? 'bad' : 'good');
  colorChip('mc-rsc',   exp.metrics.repair_security_cost > 5 ? 'bad' : 'good');
  colorChip('mc-churn', exp.metrics.security_churn > 1 ? 'warn' : 'good');
}

function setValue(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function colorChip(id, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.borderColor = {
    bad:  'rgba(239,68,68,0.4)',
    warn: 'rgba(245,158,11,0.4)',
    good: 'rgba(16,185,129,0.4)',
  }[cls] || '';
}

/* ════════════════════════════════════════════════════════════════
   REGRESSION EVENT LOG
   ════════════════════════════════════════════════════════════════ */

function renderRegressionLog(exp) {
  const card = document.getElementById('regression-log-card');
  const log  = document.getElementById('regression-log');
  const countBadge = document.getElementById('reg-count-badge');

  if (!card || !log) return;

  const events = exp.regression_events;
  card.style.display = 'block';
  if (countBadge) countBadge.textContent = `${events.length} regression event${events.length !== 1 ? 's' : ''}`;

  if (events.length === 0) {
    log.innerHTML = '<p style="color:#64748b;font-size:0.82rem;">No regression events detected in this experiment.</p>';
    return;
  }

  log.innerHTML = events.map(ev => {
    const distClass = { cross: 'dist-cross', module: 'dist-module', file: 'dist-file', local: 'dist-local' }[ev.distance] || 'dist-module';
    const distLabel = { cross: '⚡ Cross-System', module: '📦 Module-Level', file: '📄 File-Level', local: '📍 Local' }[ev.distance] || 'Module-Level';

    const crossClassBadge = ev.is_cross_class
      ? `<span class="cross-class-badge">✦ Cross-Class Regression</span>`
      : '';

    const migrationBadge = ev.is_migration
      ? `<span class="cross-class-badge" style="background:rgba(245,158,11,0.1);color:#fbbf24;">↔ Vuln Migration</span>`
      : '';

    const fixedStr = ev.fixed_cwe
      ? `Fixed: <strong>${shortCWEName(ev.fixed_cwe)}</strong> →`
      : 'Introduced at';

    return `
      <div class="reg-event">
        <div class="reg-event-icon">🔴</div>
        <div class="reg-event-content">
          <div class="reg-event-title">${shortCWEName(ev.introduced_cwe)} (${ev.introduced_cwe})</div>
          <div class="reg-event-meta">
            <span>Iteration t${ev.iteration}</span>
            <span>${fixedStr} <strong>${shortCWEName(ev.introduced_cwe)}</strong></span>
            <span class="distance-badge ${distClass}">${distLabel}</span>
            ${crossClassBadge}
            ${migrationBadge}
          </div>
        </div>
      </div>
    `;
  }).join('');
}
