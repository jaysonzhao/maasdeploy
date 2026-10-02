const POLL_MS = 30_000;
const MAX_POINTS = 30;
const pods = new Map();
let tick = 0;
const engineColors = {
  vllm: ['#2868d7', '#91acf1', '#174491'],
  llmd: ['#008f83', '#59c7b4', '#136b62'],
};
const state = document.getElementById('live-state');
const liveLabel = document.getElementById('live-label');
const notice = document.getElementById('notice');

function formatMs(seconds) {
  if (!Number.isFinite(seconds)) return '—';
  const ms = seconds * 1000;
  return ms < 100 ? `${ms.toFixed(1)} ms` : `${Math.round(ms).toLocaleString()} ms`;
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return '—';
  return `${value.toFixed(1)}%`;
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}

function shortPodName(name) {
  return name.replace(/^redhataiqwen25-7b-instruct(?:-vll)?-kserve-/, '');
}

function renderTables(samples) {
  for (const engine of ['vllm', 'llmd']) {
    const rows = samples.filter((pod) => pod.engine === engine).sort((a, b) => a.podName.localeCompare(b.podName));
    const body = document.getElementById(`pods-${engine}`);
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="3" class="empty-row">No recent samples for this deployment</td></tr>';
      continue;
    }
    body.innerHTML = rows.map((pod) => `<tr>
      <td class="pod-cell" title="${escapeHTML(pod.podName)}"><span class="pod-dot ${engine}"></span>${escapeHTML(shortPodName(pod.podName))}</td>
      <td class="number-cell">${formatMs(pod.ttftP99Seconds)}</td>
      <td class="number-cell cache-number">${formatPercent(pod.kvCacheHitPercent)}</td>
    </tr>`).join('');
  }
}

function addSample(samples) {
  tick += 1;
  for (const entry of pods.values()) {
    entry.ttft.push(null);
    entry.cache.push(null);
    entry.lastSeen = tick;
  }
  for (const sample of samples) {
    let entry = pods.get(sample.podName);
    if (!entry) {
      entry = { engine: sample.engine, ttft: Array(tick - 1).fill(null), cache: Array(tick - 1).fill(null), lastSeen: tick };
      pods.set(sample.podName, entry);
    }
    entry.engine = sample.engine;
    entry.lastSeen = tick;
    entry.ttft[tick - 1] = Number.isFinite(sample.ttftP99Seconds) ? sample.ttftP99Seconds * 1000 : null;
    entry.cache[tick - 1] = Number.isFinite(sample.kvCacheHitPercent) ? sample.kvCacheHitPercent : null;
  }
  for (const [name, entry] of pods) {
    if (tick - entry.lastSeen >= 3) pods.delete(name);
    if (entry.ttft.length > MAX_POINTS) entry.ttft.shift();
    if (entry.cache.length > MAX_POINTS) entry.cache.shift();
  }
}

function replicaColor(entry, name, engineNames) {
  const index = engineNames.indexOf(name);
  return engineColors[entry.engine][Math.min(index, engineColors[entry.engine].length - 1)];
}

function renderLegend(targetId) {
  const target = document.getElementById(targetId);
  const names = [...pods.keys()].sort();
  target.innerHTML = names.map((name) => {
    const entry = pods.get(name);
    const engineNames = names.filter((other) => pods.get(other).engine === entry.engine);
    const colorIndex = engineNames.indexOf(name);
    return `<span><i class="legend-swatch swatch-${entry.engine}-${Math.min(colorIndex, engineColors[entry.engine].length - 1)}"></i>${entry.engine === 'vllm' ? 'vLLM' : 'llm-d'} · ${escapeHTML(shortPodName(name))}</span>`;
  }).join('');
}

function drawChart(canvasId, metric, unit, emptyId, legendId) {
  const canvas = document.getElementById(canvasId);
  const empty = document.getElementById(emptyId);
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const width = rect.width;
  const height = rect.height;
  const pad = { left: 48, right: 10, top: 12, bottom: 23 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const field = metric === 'ttft' ? 'ttft' : 'cache';
  const allValues = [...pods.values()].flatMap((entry) => entry[field].filter(Number.isFinite));
  renderLegend(legendId);
  if (!allValues.length) {
    empty.hidden = false;
    ctx.clearRect(0, 0, width, height);
    return;
  }
  empty.hidden = true;
  let min = Math.min(...allValues);
  let max = Math.max(...allValues);
  const span = max - min;
  if (metric === 'cache') {
    min = Math.max(0, min - Math.max(3, span * 0.15));
    max = Math.min(100, max + Math.max(3, span * 0.15));
  } else {
    min = Math.max(0, min - Math.max(5, span * 0.15));
    max += Math.max(5, span * 0.15);
  }
  if (max === min) max = min + 1;

  ctx.clearRect(0, 0, width, height);
  ctx.font = '10px system-ui, sans-serif';
  ctx.textBaseline = 'middle';
  ctx.strokeStyle = '#edf1f5';
  ctx.fillStyle = '#98a3b1';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = pad.top + plotH * (i / 3);
    const value = max - (max - min) * (i / 3);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    ctx.textAlign = 'right';
    ctx.fillText(`${Math.round(value)}${unit}`, pad.left - 8, y);
  }

  const names = [...pods.keys()].sort();
  const historyLength = Math.max(1, ...[...pods.values()].map((entry) => entry[field].length));
  for (const name of names) {
    const entry = pods.get(name);
    const engineNames = names.filter((other) => pods.get(other).engine === entry.engine);
    const color = replicaColor(entry, name, engineNames);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    let drawing = false;
    let lastPoint = null;
    ctx.beginPath();
    entry[field].forEach((value, index) => {
      if (!Number.isFinite(value)) { drawing = false; return; }
      const x = pad.left + plotW * (index / Math.max(1, historyLength - 1));
      const y = pad.top + plotH * (1 - (value - min) / (max - min));
      if (drawing) ctx.lineTo(x, y); else { ctx.moveTo(x, y); drawing = true; }
      lastPoint = { x, y };
    });
    ctx.stroke();
    if (lastPoint) {
      ctx.beginPath(); ctx.arc(lastPoint.x, lastPoint.y, 3, 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#98a3b1';
  ctx.fillText('now', width - pad.right - 24, height - 3);
  if (tick > 1) ctx.fillText('15 min', pad.left, height - 3);
}

function drawAll() {
  drawChart('ttft-chart', 'ttft', ' ms', 'ttft-empty', 'ttft-legend');
  drawChart('cache-chart', 'cache', '%', 'cache-empty', 'cache-legend');
}

async function refresh() {
  liveLabel.textContent = 'Updating';
  try {
    const response = await fetch('/api/metrics', { cache: 'no-store', headers: { Accept: 'application/json' } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Metrics request failed (${response.status})`);
    const samples = Array.isArray(data.pods) ? data.pods : [];
    renderTables(samples);
    addSample(samples);
    drawAll();
    state.dataset.state = 'live';
    liveLabel.textContent = 'Live';
    notice.hidden = true;
    document.getElementById('updated-at').textContent = `Last updated ${new Date(data.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  } catch (error) {
    state.dataset.state = 'error';
    liveLabel.textContent = 'Delayed';
    notice.textContent = `Metrics refresh failed: ${error.message}. The app will retry automatically.`;
    notice.hidden = false;
    if (document.getElementById('updated-at').textContent === 'Last updated —') {
      document.getElementById('updated-at').textContent = 'Waiting for metrics';
    }
  }
}

window.addEventListener('resize', drawAll);
refresh();
window.setInterval(refresh, POLL_MS);
