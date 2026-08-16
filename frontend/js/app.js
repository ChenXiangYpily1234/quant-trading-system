/* ===================================================================
 * 量化交易系统 · 前端交互层
 * 六大模块：监控总览 / 详情分析 / 多基金对比 / 新闻中心 / 我的持仓 / 策略回测
 * =================================================================== */

/* ---------------- 主题与配色 ---------------- */
const PALETTE = {
  light: { up: '#e5453b', down: '#16a34a', flat: '#8a94a6', accent: '#2f6fed', warn: '#f59e0b',
           text: '#1f2937', muted: '#8a94a6', split: '#eef1f5', bg: '#ffffff' },
  dark:  { up: '#f0564b', down: '#22c55e', flat: '#7f8b9e', accent: '#4d86ff', warn: '#f59e0b',
           text: '#e8edf5', muted: '#7f8b9e', split: '#242d3b', bg: '#161c26' },
};
let theme = localStorage.getItem('qts_theme') || 'light';
const C = () => PALETTE[theme];

/* ---------------- 全局状态 ---------------- */
const S = {
  funds: [], health: null,
  tab: 'overview',
  selected: null,
  ov: { filter: 'all', sort: 'focus', view: 'card', tableSort: null, tableDesc: true },
  dt: { days: 60, sub: 'macd', data: null,
        inds: { ma5: true, ma20: true, ma60: false, boll: false, pred: true } },
  cmp: { picked: new Set(), days: 60, data: null },
  nw: { q: '', sent: '', tag: '', sort: 'relevance', data: null },
  pf: { data: null },
  bt: { data: null },
  dca: { data: null },
  reb: { data: null, method: 'risk_parity' },
  trend: { days: 250, metric: 'norm', funds: new Set(), loaded: false, data: null },
  interval: 15000, timer: null,
  alerts: JSON.parse(localStorage.getItem('qts_alerts') || '[]'),
  fired: [],
};
const CH = {};   // ECharts 实例

/* ---------------- 工具 ---------------- */
const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));
const fmt = (v, d = 4) => (v == null || isNaN(v)) ? '—' : Number(v).toFixed(d);
const pct = (v, d = 2) => (v == null || isNaN(v)) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%';
const colorFor = (v) => v > 0 ? C().up : (v < 0 ? C().down : C().muted);
const num = (v) => (v == null || isNaN(v)) ? -Infinity : Number(v);

function dirBadge(dir) {
  if (dir === 'up') return '<span class="badge up">看多 ↗</span>';
  if (dir === 'down') return '<span class="badge down">看空 ↘</span>';
  return '<span class="badge flat">震荡 →</span>';
}

// 估值温度配色：低估(冷)蓝 · 适中灰 · 高估(热)红
function valColor(label) {
  if (label === '低估') return '#2f6fed';
  if (label === '高估') return '#e5453b';
  return '#94a3b8';
}

let toastTimer = null;
function toast(msg, kind = '') {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.className = 'toast', 2400);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) {
    let msg = '请求失败';
    try { const j = await r.json(); msg = j.detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}

function chart(id) {
  if (CH[id]) { CH[id].resize(); return CH[id]; }
  const el = $(id);
  if (!el) return null;
  CH[id] = echarts.init(el, null, { renderer: 'canvas' });
  return CH[id];
}
function disposeCharts() { Object.keys(CH).forEach(k => { CH[k].dispose(); delete CH[k]; }); }

function axisBase() {
  return {
    axisLabel: { fontSize: 10, color: C().muted },
    axisLine: { lineStyle: { color: C().split } },
    splitLine: { lineStyle: { color: C().split } },
  };
}
function tipBase() {
  return {
    trigger: 'axis',
    backgroundColor: theme === 'dark' ? '#1f2937' : '#fff',
    borderColor: C().split,
    textStyle: { color: C().text, fontSize: 11 },
    axisPointer: { type: 'cross', label: { backgroundColor: C().accent } },
  };
}

/* 迷你走势图（内联 SVG，轻量无实例开销） */
function sparkSvg(vals) {
  if (!vals || vals.length < 2) return '<div class="spark"></div>';
  const w = 100, h = 34, min = Math.min(...vals), max = Math.max(...vals);
  const span = (max - min) || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(2)},${(h - (v - min) / span * (h - 4) - 2).toFixed(2)}`);
  const rising = vals[vals.length - 1] >= vals[0];
  const col = rising ? C().up : C().down;
  return `<div class="spark"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polyline points="${pts.join(' ')}" fill="none" stroke="${col}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
    <polyline points="0,${h} ${pts.join(' ')} ${w},${h}" fill="${col}" opacity="0.10" stroke="none"/>
  </svg></div>`;
}

/* ---------------- 弹层 ---------------- */
function closeLayer() { $('layer').innerHTML = ''; }
function modal(title, bodyHtml, onOk, okText = '确定') {
  $('layer').innerHTML = `<div class="mask" id="mask">
    <div class="modal"><h3>${title}</h3><div>${bodyHtml}</div>
      <div class="actions">
        <button class="btn" id="m-cancel">取消</button>
        <button class="btn primary" id="m-ok">${okText}</button>
      </div>
    </div></div>`;
  $('mask').onclick = (e) => { if (e.target.id === 'mask') closeLayer(); };
  $('m-cancel').onclick = closeLayer;
  $('m-ok').onclick = () => onOk && onOk();
}

/* =========================================================
 * 健康状态
 * ======================================================= */
async function loadHealth() {
  try {
    const h = await api('/api/health');
    S.health = h;
    $('pill-llm').textContent = '决策引擎：' + (h.llm_enabled ? `大模型 ${h.llm_model}` : '规则引擎(内置)');
    $('pill-llm').className = 'pill ' + (h.llm_enabled ? 'real' : 'sim');
    $('pill-universe').textContent = `基金库：${(h.universe_size || 0).toLocaleString()} 只可搜索`;
  } catch (e) { $('pill-llm').textContent = '决策引擎：离线'; }
}

/* =========================================================
 * TAB 1：监控总览
 * ======================================================= */
async function loadFunds(silent) {
  if (!silent && !S.funds.length) $('ov-body').innerHTML = '<div class="loading">加载基金数据</div>';
  S.funds = await api('/api/funds');
  if (!S.selected && S.funds.length) S.selected = S.funds[0].code;
  checkAlerts();
  renderOverview();
  syncFundSelectors();
  const anyReal = S.funds.some(f => f.data_source === 'real');
  const anySim = S.funds.some(f => f.data_source !== 'real');
  const p = $('pill-source');
  p.textContent = '数据源：' + (anyReal && !anySim ? '真实净值' : (!anyReal ? '模拟(降级)' : '真实+模拟'));
  p.className = 'pill ' + (anySim ? 'sim' : 'real');
  $('pill-update').textContent = '更新：' + new Date().toLocaleTimeString('zh-CN');
  buildTrendChips();
  if (!S.trend.loaded) loadTrend();
}

/* ---------------- 历史净值走势 ---------------- */
const TREND_COLORS = ['#e5453b', '#2f6fed', '#16a34a', '#f59e0b', '#8b5cf6',
                      '#06b6d4', '#ec4899', '#64748b'];

function buildTrendChips() {
  const box = $('ov-trend-funds');
  if (!box) return;
  // 首次进入：默认勾选重点基金
  if (S.trend.funds.size === 0) {
    S.funds.filter(f => f.focus).forEach(f => S.trend.funds.add(f.code));
  }
  // 仅保留仍存在于自选列表中的代码（被移出的不再展示/绘制）
  S.trend.funds.forEach(c => { if (!S.funds.some(f => f.code === c)) S.trend.funds.delete(c); });
  if (S.trend.funds.size === 0) S.funds.slice(0, 3).forEach(f => S.trend.funds.add(f.code));
  box.innerHTML = S.funds.map(f =>
    `<span class="chip ${S.trend.funds.has(f.code) ? 'on' : ''}" data-code="${f.code}">${f.focus ? '★ ' : ''}${esc(f.name)}</span>`).join('');
}

async function loadTrend() {
  const codes = [...S.trend.funds];
  const el = $('ov-trend-chart');
  if (!codes.length) {
    S.trend.loaded = true; S.trend.data = null;
    if (el) el.innerHTML = '<div class="empty">请在上方勾选要查看的基金</div>';
    return;
  }
  if (el) el.innerHTML = '<div class="loading">加载历史净值…</div>';
  try {
    const data = await api(`/api/history?codes=${codes.join(',')}&days=${S.trend.days}`);
    S.trend.data = data;
    S.trend.loaded = true;
    renderTrendChart(data);
  } catch (e) {
    const c = $('ov-trend-chart');
    if (c) c.innerHTML = `<div class="empty">走势加载失败：${esc(e.message)}</div>`;
  }
}

function renderTrendChart(data) {
  const el = $('ov-trend-chart');
  if (!el) return;
  el.innerHTML = '';
  const inst = chart('ov-trend-chart');
  if (!inst) return;
  const norm = S.trend.metric === 'norm';
  const x = data.series[0] ? data.series[0].dates : [];
  const series = data.series.map((s, i) => {
    const arr = norm
      ? (() => { const base = s.navs[0] || 1; return s.navs.map(v => +((v / base - 1) * 100).toFixed(2)); })()
      : s.navs;
    return {
      name: s.name, type: 'line', data: arr, smooth: true, showSymbol: false,
      lineStyle: { width: 2 }, itemStyle: { color: TREND_COLORS[i % TREND_COLORS.length] },
      emphasis: { focus: 'series' },
    };
  });
  inst.setOption({
    color: TREND_COLORS,
    grid: { left: 54, right: 18, top: 38, bottom: 58 },
    tooltip: Object.assign(tipBase(), {
      valueFormatter: (v) => norm ? pct(v) : (v == null ? '—' : Number(v).toFixed(4)),
    }),
    legend: { top: 4, type: 'scroll', textStyle: { color: C().text, fontSize: 11 } },
    xAxis: Object.assign({ type: 'category', data: x, boundaryGap: false }, axisBase()),
    yAxis: Object.assign({
      type: 'value', scale: true,
      name: norm ? '累计收益 %' : '单位净值',
      nameTextStyle: { color: C().muted, fontSize: 10 },
    }, axisBase()),
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 16, bottom: 16, start: 0, end: 100,
        borderColor: C().split, textStyle: { color: C().muted, fontSize: 9 } },
    ],
    series,
  }, true);
}

function wireTrend() {
  const range = $('ov-trend-range');
  if (range) range.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    S.trend.days = +b.dataset.d;
    $$('#ov-trend-range button').forEach(x => x.classList.toggle('on', x === b));
    loadTrend();
  });
  const metric = $('ov-trend-metric');
  if (metric) metric.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    S.trend.metric = b.dataset.m;
    $$('#ov-trend-metric button').forEach(x => x.classList.toggle('on', x === b));
    if (S.trend.data) renderTrendChart(S.trend.data); else loadTrend();
  });
  const funds = $('ov-trend-funds');
  if (funds) funds.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip'); if (!chip) return;
    const code = chip.dataset.code;
    if (S.trend.funds.has(code)) S.trend.funds.delete(code); else S.trend.funds.add(code);
    chip.classList.toggle('on', S.trend.funds.has(code));
    loadTrend();
  });
}

function filteredFunds() {
  let list = S.funds.slice();
  const f = S.ov.filter;
  if (f === 'focus') list = list.filter(x => x.focus);
  else if (f === 'up') list = list.filter(x => x.direction === 'up');
  else if (f === 'down') list = list.filter(x => x.direction === 'down');
  else if (f === 'add') list = list.filter(x => (x.advice || '').includes('加仓') || (x.advice || '').includes('买入'));
  else if (f === 'held') list = list.filter(x => x.held);

  const s = S.ov.sort;
  const cmp = {
    focus: (a, b) => (b.focus - a.focus) || (num(b.day_change_pct) - num(a.day_change_pct)),
    day: (a, b) => num(b.day_change_pct) - num(a.day_change_pct),
    ret20: (a, b) => num(b.return_20d) - num(a.return_20d),
    pred: (a, b) => num(b.predicted_change_pct) - num(a.predicted_change_pct),
    conf: (a, b) => num(b.confidence) - num(a.confidence),
    name: (a, b) => a.name.localeCompare(b.name, 'zh'),
  }[s];
  return list.sort(cmp);
}

function renderKpis() {
  const fs = S.funds;
  const up = fs.filter(f => f.direction === 'up').length;
  const down = fs.filter(f => f.direction === 'down').length;
  const avgConf = fs.length ? fs.reduce((a, b) => a + (b.confidence || 0), 0) / fs.length : 0;
  const avgDay = fs.length ? fs.reduce((a, b) => a + (b.day_change_pct || 0), 0) / fs.length : 0;
  const advCount = fs.filter(f => (f.advice || '').includes('加仓') || (f.advice || '').includes('买入')).length;
  const real = fs.filter(f => f.data_source === 'real').length;
  const items = [
    { k: '监控基金', v: fs.length, f: 'all' },
    { k: '平均当日涨跌', v: pct(avgDay), col: colorFor(avgDay), f: 'all' },
    { k: '看多', v: up, col: C().up, f: 'up' },
    { k: '看空', v: down, col: C().down, f: 'down' },
    { k: '建议加仓', v: advCount, col: C().accent, f: 'add' },
    { k: '平均置信度', v: Math.round(avgConf * 100) + '%', f: 'all' },
    { k: '真实数据源', v: `${real}/${fs.length}`, f: 'all' },
    { k: '重点关注', v: fs.filter(f => f.focus).length, col: C().up, f: 'focus' },
  ];
  $('ov-kpis').innerHTML = items.map(i =>
    `<div class="kpi clickable" data-kf="${i.f}"><div class="k">${i.k}</div>
      <div class="v" style="color:${i.col || 'inherit'}">${i.v}</div></div>`).join('');
}

function fundCardHtml(f) {
  const estCol = colorFor(f.estimate_change_pct);
  return `<div class="fund-card ${f.code === S.selected ? 'active' : ''} ${f.focus ? 'focus' : ''}" data-code="${f.code}">
    <div class="card-actions">
      <button data-act="focus" class="${f.focus ? 'on' : ''}" title="${f.focus ? '取消重点关注' : '设为重点关注'}">★</button>
      <button data-act="hold" title="加入持仓">＋</button>
      <button data-act="alert" title="设置价格提醒">🔔</button>
      <button data-act="del" class="del" title="移出自选">✕</button>
    </div>
    <div class="cat">${esc(f.category)}
      ${f.focus ? '<span class="focus-badge">★重点</span>' : ''}
      ${f.held ? '<span class="held-badge">持仓中</span>' : ''}</div>
    <div class="name" title="${esc(f.name)}">${esc(f.name)}</div>
    <div class="code"><span class="dot ${f.data_source === 'real' ? 'real' : 'sim'}"></span> ${f.code} · ${f.latest_date || '—'}</div>
    <div class="nav-row">
      <span class="nav">${fmt(f.latest_nav)}</span>
      <span class="chg" style="color:${colorFor(f.day_change_pct)}">${pct(f.day_change_pct)}</span>
    </div>
    <div class="est">盘中模拟估值 ${fmt(f.estimate_nav)} <span style="color:${estCol}">${pct(f.estimate_change_pct)}</span>
      · 20日 <span style="color:${colorFor(f.return_20d)}">${pct(f.return_20d)}</span></div>
    ${sparkSvg(f.sparkline)}
    <div class="foot">
      ${dirBadge(f.direction)}
      <span class="advice-chip">${esc(f.advice || '—')}</span>
      ${f.valuation ? `<span class="val-badge" style="color:${valColor(f.valuation.label)};border-color:${valColor(f.valuation.label)}">估值·${esc(f.valuation.label)} ${f.valuation.temp}</span>` : ''}
      <span class="conf" style="margin-left:auto">置信 ${Math.round((f.confidence || 0) * 100)}%</span>
    </div>
  </div>`;
}

const TABLE_COLS = [
  { k: 'name', t: '基金', sort: (a, b) => a.name.localeCompare(b.name, 'zh') },
  { k: 'latest_nav', t: '最新净值' },
  { k: 'day_change_pct', t: '当日' },
  { k: 'return_20d', t: '近20日' },
  { k: 'predicted_change_pct', t: '预测5日' },
  { k: 'confidence', t: '置信度' },
  { k: 'advice', t: '建议', nosort: true },
  { k: 'position_action', t: '仓位动作', nosort: true },
  { k: 'risk_level', t: '风险', nosort: true },
  { k: 'act', t: '操作', nosort: true },
];

function renderTable(list) {
  if (S.ov.tableSort) {
    const key = S.ov.tableSort;
    list = list.slice().sort((a, b) => {
      const va = a[key], vb = b[key];
      const r = (typeof va === 'string') ? String(va).localeCompare(String(vb), 'zh') : (num(va) - num(vb));
      return S.ov.tableDesc ? -r : r;
    });
  }
  const th = TABLE_COLS.map(c => {
    const on = S.ov.tableSort === c.k;
    return `<th class="${c.nosort ? 'nosort' : ''}" data-col="${c.k}">${c.t}${on ? `<span class="arrow">${S.ov.tableDesc ? '▼' : '▲'}</span>` : ''}</th>`;
  }).join('');
  const rows = list.map(f => `<tr data-code="${f.code}">
    <td class="name-cell">${f.focus ? '<span class="focus-badge">★</span> ' : ''}${esc(f.name)}
      <span style="color:var(--muted);font-size:11px">${f.code}</span></td>
    <td>${fmt(f.latest_nav)}</td>
    <td style="color:${colorFor(f.day_change_pct)}">${pct(f.day_change_pct)}</td>
    <td style="color:${colorFor(f.return_20d)}">${pct(f.return_20d)}</td>
    <td style="color:${colorFor(f.predicted_change_pct)}">${pct(f.predicted_change_pct)}</td>
    <td>${Math.round((f.confidence || 0) * 100)}%</td>
    <td><span class="advice-chip">${esc(f.advice || '—')}</span></td>
    <td>${esc(f.position_action || '—')}</td>
    <td>${esc(f.risk_level || '—')}</td>
    <td><button class="btn sm" data-act="focus">${f.focus ? '取消重点' : '设重点'}</button>
        <button class="btn sm" data-act="hold">持仓</button>
        <button class="btn sm danger" data-act="del">移除</button></td>
  </tr>`).join('');
  return `<div class="table-wrap"><table class="grid"><thead><tr>${th}</tr></thead>
    <tbody>${rows || '<tr><td colspan="10" class="empty">没有符合条件的基金</td></tr>'}</tbody></table></div>`;
}

function renderOverview() {
  renderKpis();
  const list = filteredFunds();
  $('ov-count').textContent = `共 ${S.funds.length} 只，当前显示 ${list.length} 只`;
  const body = $('ov-body');
  if (!list.length) {
    body.innerHTML = '<div class="empty">没有符合条件的基金，换个筛选条件试试，或在顶部搜索框添加基金。</div>';
    return;
  }
  body.innerHTML = S.ov.view === 'card'
    ? `<div class="fund-grid">${list.map(fundCardHtml).join('')}</div>`
    : renderTable(list);
}

/* 卡片/表格交互（事件委托） */
$('ov-body').addEventListener('click', async (e) => {
  const actBtn = e.target.closest('[data-act]');
  const host = e.target.closest('[data-code]');
  if (!host) return;
  const code = host.dataset.code;
  const fund = S.funds.find(f => f.code === code);
  if (actBtn) {
    e.stopPropagation();
    const act = actBtn.dataset.act;
    if (act === 'focus') {
      try {
        const r = await api(`/api/funds/${code}/focus`, { method: 'POST' });
        fund.focus = r.focus;
        renderOverview();
        toast(r.focus ? `已将「${fund.name}」设为重点关注` : `已取消「${fund.name}」的重点关注`, 'ok');
      } catch (err) { toast(err.message, 'err'); }
    } else if (act === 'hold') {
      openHoldingModal(fund);
    } else if (act === 'alert') {
      openAlertModal(fund);
    } else if (act === 'del') {
      modal('移出自选', `确定将 <b>${esc(fund.name)}</b>（${code}）移出自选监控列表？<div class="hint" style="margin-top:6px">持仓记录不会被删除。</div>`, async () => {
        try {
          await api(`/api/funds/${code}`, { method: 'DELETE' });
          closeLayer();
          if (S.selected === code) S.selected = null;
          await loadFunds(true);
          toast('已移出自选', 'ok');
        } catch (err) { toast(err.message, 'err'); }
      }, '移除');
    }
    return;
  }
  // 点击卡片/行 -> 进入详情
  S.selected = code;
  setTab('detail');
});

$('ov-body').addEventListener('click', (e) => {
  const th = e.target.closest('th[data-col]');
  if (!th || th.classList.contains('nosort')) return;
  const col = th.dataset.col;
  if (S.ov.tableSort === col) S.ov.tableDesc = !S.ov.tableDesc;
  else { S.ov.tableSort = col; S.ov.tableDesc = true; }
  renderOverview();
});

$('ov-kpis').addEventListener('click', (e) => {
  const k = e.target.closest('[data-kf]');
  if (!k) return;
  S.ov.filter = k.dataset.kf;
  $$('#ov-filters .chip').forEach(c => c.classList.toggle('on', c.dataset.f === S.ov.filter));
  renderOverview();
});

$('ov-filters').addEventListener('click', (e) => {
  const c = e.target.closest('.chip'); if (!c) return;
  S.ov.filter = c.dataset.f;
  $$('#ov-filters .chip').forEach(x => x.classList.toggle('on', x === c));
  renderOverview();
});
$('ov-sort').onchange = (e) => { S.ov.sort = e.target.value; S.ov.tableSort = null; renderOverview(); };
$('ov-view').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  S.ov.view = b.dataset.v;
  $$('#ov-view button').forEach(x => x.classList.toggle('on', x === b));
  renderOverview();
});

/* =========================================================
 * TAB 2：详情分析
 * ======================================================= */
function syncFundSelectors() {
  const opts = S.funds.map(f => `<option value="${f.code}">${f.focus ? '★ ' : ''}${esc(f.name)} (${f.code})</option>`).join('');
  ['dt-fund', 'bt-code', 'dca-code'].forEach(id => {
    const el = $(id); if (!el) return;
    const cur = el.value;
    el.innerHTML = opts;
    el.value = (cur && S.funds.some(f => f.code === cur)) ? cur : (S.selected || (S.funds[0] || {}).code || '');
  });
  const pf = $('pf-code');
  if (pf) {
    const cur = pf.value;
    pf.innerHTML = opts;
    if (cur) pf.value = cur;
  }
  // 对比选择器
  const picker = $('cmp-picker');
  if (picker) {
    picker.innerHTML = S.funds.map(f =>
      `<span class="chip ${S.cmp.picked.has(f.code) ? 'on' : ''}" data-code="${f.code}">${f.focus ? '★' : ''}${esc(f.name)}</span>`).join('');
  }
}

async function loadDetail() {
  const code = S.selected || (S.funds[0] || {}).code;
  if (!code) return;
  S.selected = code;
  $('dt-fund').value = code;
  $('dt-analysis').innerHTML = '<div class="loading">研判中</div>';
  try {
    const d = await api(`/api/funds/${code}?days=${S.dt.days}`);
    S.dt.data = d;
    renderDetailChart();
    renderDetailKpis();
    renderAnalysis(d.recommendation, d);
  } catch (e) {
    $('dt-analysis').innerHTML = `<div class="empty">加载失败：${esc(e.message)}</div>`;
  }
}

function renderDetailChart() {
  const d = S.dt.data; if (!d) return;
  const dates = d.history.map(h => h.date);
  const navs = d.history.map(h => h.nav);
  const showPred = S.dt.inds.pred;
  const fut = showPred ? d.prediction.future_dates : [];
  const allDates = dates.concat(fut);
  const padN = fut.length;
  const pad = (arr) => arr.concat(Array(padN).fill(null));
  const n = dates.length;

  const series = [{
    name: '单位净值', type: 'line', data: pad(navs), smooth: true, symbol: 'none',
    lineStyle: { width: 2.2, color: C().accent }, z: 6,
    areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: theme === 'dark' ? 'rgba(77,134,255,.28)' : 'rgba(47,111,237,.20)' },
      { offset: 1, color: 'rgba(47,111,237,0)' }]) },
  }];
  const I = d.indicators || {};
  if (S.dt.inds.ma5 && I.ma5) series.push({ name: 'MA5', type: 'line', data: pad(I.ma5), smooth: true, symbol: 'none', lineStyle: { width: 1.2, color: '#f5a623' } });
  if (S.dt.inds.ma20 && I.ma20) series.push({ name: 'MA20', type: 'line', data: pad(I.ma20), smooth: true, symbol: 'none', lineStyle: { width: 1.2, color: '#9b59b6' } });
  if (S.dt.inds.ma60 && I.ma60) series.push({ name: 'MA60', type: 'line', data: pad(I.ma60), smooth: true, symbol: 'none', lineStyle: { width: 1.2, color: '#0ea5e9' } });
  if (S.dt.inds.boll && I.boll) {
    series.push({ name: 'BOLL上轨', type: 'line', data: pad(I.boll.upper), symbol: 'none', lineStyle: { width: 1, color: C().muted, type: 'dashed' } });
    series.push({ name: 'BOLL下轨', type: 'line', data: pad(I.boll.lower), symbol: 'none', lineStyle: { width: 1, color: C().muted, type: 'dashed' } });
  }
  if (showPred) {
    const p = d.prediction;
    const predLine = Array(n).fill(null); predLine[n - 1] = navs[n - 1];
    p.future_nav.forEach(v => predLine.push(v));
    const bandLow = Array(n).fill(null); bandLow[n - 1] = navs[n - 1];
    const bandDelta = Array(n).fill(null);
    p.future_lower.forEach(v => bandLow.push(v));
    p.future_upper.forEach((v, i) => bandDelta.push(+(v - p.future_lower[i]).toFixed(4)));
    series.push({ name: '置信区间', type: 'line', data: bandLow, stack: 'cf', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, z: 1, tooltip: { show: false } });
    series.push({ name: '置信区间', type: 'line', data: bandDelta, stack: 'cf', symbol: 'none', lineStyle: { opacity: 0 },
      areaStyle: { color: theme === 'dark' ? 'rgba(77,134,255,.16)' : 'rgba(47,111,237,.12)' }, z: 1, tooltip: { show: false } });
    series.push({
      name: `预测(${p.horizon_days}日)`, type: 'line', data: predLine, smooth: true,
      symbol: 'circle', symbolSize: 5, z: 7,
      lineStyle: { width: 2, color: p.direction === 'down' ? C().down : C().up, type: 'dashed' },
      itemStyle: { color: p.direction === 'down' ? C().down : C().up },
      markLine: { silent: true, symbol: 'none', label: { formatter: '今日', fontSize: 10, color: C().muted },
        lineStyle: { color: C().muted, type: 'dotted' }, data: [{ xAxis: dates[n - 1] }] },
    });
  }

  const c = chart('dt-chart');
  c.group = 'dt';
  c.setOption({
    animation: false,
    tooltip: tipBase(),
    legend: { top: 0, right: 0, textStyle: { fontSize: 11, color: C().muted }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 52, right: 18, top: 32, bottom: 46 },
    xAxis: { type: 'category', data: allDates, boundaryGap: false, ...axisBase() },
    yAxis: { type: 'value', scale: true, ...axisBase() },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 16, bottom: 8, borderColor: C().split,
        textStyle: { fontSize: 9, color: C().muted }, start: 0, end: 100 },
    ],
    series,
  }, true);

  renderSubChart(allDates, padN);
  try { echarts.connect('dt'); } catch (e) {}
}

function renderSubChart(allDates, padN) {
  const d = S.dt.data;
  const el = $('dt-sub-chart');
  if (S.dt.sub === 'none') { el.style.display = 'none'; if (CH['dt-sub-chart']) { CH['dt-sub-chart'].dispose(); delete CH['dt-sub-chart']; } return; }
  el.style.display = 'block';
  const I = d.indicators || {};
  const pad = (arr) => (arr || []).concat(Array(padN).fill(null));
  let series = [], yAxis = { type: 'value', ...axisBase() }, extra = {};

  if (S.dt.sub === 'macd') {
    series = [
      { name: 'MACD柱', type: 'bar', data: pad(I.macd?.hist), itemStyle: {
          color: (p) => p.value >= 0 ? C().up : C().down }, barWidth: '55%' },
      { name: 'DIF', type: 'line', data: pad(I.macd?.dif), symbol: 'none', lineStyle: { width: 1.2, color: '#f5a623' } },
      { name: 'DEA', type: 'line', data: pad(I.macd?.dea), symbol: 'none', lineStyle: { width: 1.2, color: '#9b59b6' } },
    ];
  } else if (S.dt.sub === 'rsi') {
    series = [{ name: 'RSI14', type: 'line', data: pad(I.rsi), symbol: 'none', lineStyle: { width: 1.6, color: C().accent },
      markLine: { silent: true, symbol: 'none', label: { fontSize: 9, color: C().muted },
        lineStyle: { type: 'dashed', color: C().muted },
        data: [{ yAxis: 70, name: '超买' }, { yAxis: 30, name: '超卖' }] } }];
    yAxis = { type: 'value', min: 0, max: 100, ...axisBase() };
  } else {
    series = [
      { name: 'K', type: 'line', data: pad(I.kdj?.k), symbol: 'none', lineStyle: { width: 1.3, color: '#f5a623' } },
      { name: 'D', type: 'line', data: pad(I.kdj?.d), symbol: 'none', lineStyle: { width: 1.3, color: C().accent } },
      { name: 'J', type: 'line', data: pad(I.kdj?.j), symbol: 'none', lineStyle: { width: 1, color: '#9b59b6' } },
    ];
  }

  const c = chart('dt-sub-chart');
  c.group = 'dt';
  c.setOption({
    animation: false,
    tooltip: tipBase(),
    legend: { top: 0, right: 0, textStyle: { fontSize: 10, color: C().muted }, itemWidth: 12, itemHeight: 7 },
    grid: { left: 52, right: 18, top: 24, bottom: 22 },
    xAxis: { type: 'category', data: allDates, boundaryGap: false, axisLabel: { fontSize: 9, color: C().muted }, axisLine: { lineStyle: { color: C().split } } },
    yAxis,
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series, ...extra,
  }, true);
}

function renderDetailKpis() {
  const d = S.dt.data; if (!d) return;
  const st = d.stats || {}, ind = d.prediction.indicators || {};
  const items = [
    ['区间收益', pct(st.total_return), colorFor(st.total_return)],
    ['年化收益', pct(st.annual_return), colorFor(st.annual_return)],
    ['最大回撤', pct(st.max_drawdown), C().down],
    ['年化波动', pct(st.volatility), ''],
    ['夏普比率', (st.sharpe ?? '—'), (st.sharpe > 1 ? C().up : '')],
    ['索提诺比率', (st.sortino ?? '—'), (st.sortino > 1 ? C().up : '')],
    ['卡玛比率', (st.calmar ?? '—'), (st.calmar > 1 ? C().up : '')],
    ['下行波动', pct(st.downside_dev), ''],
    ['上涨天数占比', (st.win_rate ?? '—') + '%', ''],
    ['近5日动量', pct(ind.momentum5), colorFor(ind.momentum5)],
    ['近20日动量', pct(ind.momentum20), colorFor(ind.momentum20)],
    ['RSI(14)', ind.rsi, (ind.rsi > 70 ? C().up : ind.rsi < 30 ? C().down : '')],
    ['日波动率', (ind.volatility ?? '—') + '%', ''],
  ];
  $('dt-kpis').innerHTML = items.map(([k, v, col]) =>
    `<div class="kpi"><div class="k">${k}</div><div class="v" style="color:${col || 'inherit'};font-size:15px">${v}</div></div>`).join('');
}

function renderAnalysis(rec, d) {
  $('dt-analysis').innerHTML = `
    <div class="analysis">
      <div class="row"><span class="label">基金</span><span class="val"><b>${esc(d.name)}</b>（${d.code}）· ${esc(d.category)}
        ${d.focus ? '<span class="focus-badge">★重点</span>' : ''}
        <span class="tag ${d.data_source === 'real' ? 'pos' : 'neu'}">${d.data_source === 'real' ? '真实净值' : '模拟数据'}</span>
        <span class="hint">最新净值日 ${d.latest_date || '—'} · 样本 ${d.days} 交易日</span></span></div>
      <div class="row"><span class="label">研判引擎</span><span class="val"><span class="engine-tag">${rec.engine === 'llm' ? '大模型 LLM' : '规则引擎(内置)'}</span>
        <span class="hint">生成于 ${esc(rec.generated_at || '')}</span></span></div>
      <div class="row"><span class="label">走势预测</span><span class="val">${esc(rec.trend_prediction)}${d.valuation ? ` · <b style="color:${valColor(d.valuation.label)}">估值·${esc(d.valuation.label)}</b>（温度 ${d.valuation.temp}，净值处历史 ${d.valuation.nav_pct_rank}% 分位，相对长期均线 ${d.valuation.ma_ratio})` : ''}
        ${rec.predicted_nav ? ` · 目标净值 <b>${fmt(rec.predicted_nav)}</b> (<span style="color:${colorFor(rec.predicted_change_pct)}">${pct(rec.predicted_change_pct)}</span>)` : ''}
        · 置信 <b>${Math.round((rec.confidence || 0) * 100)}%</b></span></div>
      <div class="row"><span class="label">操作建议</span><span class="val">
        <b style="color:${C().accent};font-size:14px">${esc(rec.advice)}</b>
        ｜ 仓位动作：<b>${esc(rec.position_action)}</b> ｜ 风险等级：<b style="color:${rec.risk_level === '高' ? C().up : ''}">${esc(rec.risk_level)}</b></span></div>
      <div class="row"><span class="label">分析依据</span><span class="val">${esc(rec.reasoning)}</span></div>
      <div class="row"><span class="label">新闻情绪</span><span class="val">均值 <b style="color:${colorFor(d.sentiment.avg_sentiment)}">${d.sentiment.avg_sentiment}</b>
        · 利好 ${d.sentiment.pos} 条 / 利空 ${d.sentiment.neg} 条（样本 ${d.sentiment.count}）
        <button class="btn sm" id="an-news">查看相关资讯</button></span></div>
      ${rec.key_news && rec.key_news.length ? `<div class="row"><span class="label">关键新闻</span><span class="val">${rec.key_news.map(x => '· ' + esc(x)).join('<br>')}</span></div>` : ''}
    </div>`;
  const b = $('an-news');
  if (b) b.onclick = () => { S.nw.q = ''; setTab('news'); };
}

$('dt-fund').onchange = (e) => { S.selected = e.target.value; loadDetail(); };
$('dt-range').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  S.dt.days = +b.dataset.d;
  $$('#dt-range button').forEach(x => x.classList.toggle('on', x === b));
  loadDetail();
});
$('dt-inds').addEventListener('click', (e) => {
  const c = e.target.closest('.chip'); if (!c) return;
  const k = c.dataset.i;
  S.dt.inds[k] = !S.dt.inds[k];
  c.classList.toggle('on', S.dt.inds[k]);
  renderDetailChart();
});
$('dt-sub').onchange = (e) => { S.dt.sub = e.target.value; renderDetailChart(); };
$('dt-csv').onclick = () => {
  if (!S.selected) return;
  window.open(`/api/export/${S.selected}.csv?days=${Math.max(S.dt.days, 120)}`, '_blank');
  toast('CSV 已开始下载', 'ok');
};
$('dt-ai').onclick = async () => {
  if (!S.selected) return;
  toast('正在重新研判…');
  try {
    const rec = await api(`/api/analysis/${S.selected}?force=1`);
    await loadDetail();
    toast(`研判完成：${rec.advice}`, 'ok');
  } catch (e) { toast(e.message, 'err'); }
};
$('dt-hold').onclick = () => {
  const f = S.funds.find(x => x.code === S.selected) || S.dt.data;
  if (f) openHoldingModal(f);
};
$('dt-fs').onclick = () => {
  const el = $('dt-chart');
  const on = el.classList.toggle('chart-fs');
  $('dt-fs').textContent = on ? '⛶ 退出全屏' : '⛶ 全屏';
  setTimeout(() => CH['dt-chart'] && CH['dt-chart'].resize(), 60);
};

/* =========================================================
 * TAB 3：多基金对比
 * ======================================================= */
$('cmp-picker').addEventListener('click', (e) => {
  const c = e.target.closest('.chip'); if (!c) return;
  const code = c.dataset.code;
  if (S.cmp.picked.has(code)) S.cmp.picked.delete(code);
  else {
    if (S.cmp.picked.size >= 8) return toast('最多对比 8 只基金', 'err');
    S.cmp.picked.add(code);
  }
  c.classList.toggle('on', S.cmp.picked.has(code));
});
$('cmp-all').onclick = () => {
  S.cmp.picked = new Set(S.funds.slice(0, 8).map(f => f.code));
  syncFundSelectors();
};
$('cmp-none').onclick = () => { S.cmp.picked.clear(); syncFundSelectors(); };
$('cmp-days').onchange = (e) => { S.cmp.days = +e.target.value; };
$('cmp-run').onclick = runCompare;

async function runCompare() {
  if (!S.cmp.picked.size) {
    S.cmp.picked = new Set(S.funds.filter(f => f.focus).map(f => f.code));
    if (!S.cmp.picked.size) S.cmp.picked = new Set(S.funds.slice(0, 4).map(f => f.code));
    syncFundSelectors();
  }
  const codes = Array.from(S.cmp.picked).join(',');
  $('cmp-stats').innerHTML = '<div class="loading">对比计算中</div>';
  try {
    const d = await api(`/api/compare?codes=${codes}&days=${S.cmp.days}`);
    S.cmp.data = d;
    renderCompare();
  } catch (e) {
    $('cmp-stats').innerHTML = `<div class="empty">对比失败：${esc(e.message)}</div>`;
  }
}

function renderCompare() {
  const d = S.cmp.data; if (!d) return;
  const colors = ['#2f6fed', '#e5453b', '#16a34a', '#f5a623', '#9b59b6', '#0ea5e9', '#ec4899', '#14b8a6'];
  const base = d.series.reduce((a, b) => a.dates.length >= b.dates.length ? a : b, d.series[0]);
  chart('cmp-chart').setOption({
    animation: false,
    tooltip: { ...tipBase(), valueFormatter: (v) => (v == null ? '—' : v + '%') },
    legend: { top: 0, textStyle: { fontSize: 11, color: C().muted }, itemWidth: 14, itemHeight: 8, type: 'scroll' },
    grid: { left: 50, right: 18, top: 34, bottom: 40 },
    xAxis: { type: 'category', data: base.dates, boundaryGap: false, ...axisBase() },
    yAxis: { type: 'value', axisLabel: { formatter: '{value}%', fontSize: 10, color: C().muted },
             axisLine: { lineStyle: { color: C().split } }, splitLine: { lineStyle: { color: C().split } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 15, bottom: 6, borderColor: C().split, textStyle: { fontSize: 9, color: C().muted } }],
    series: d.series.map((s, i) => ({
      name: s.name, type: 'line', data: s.normalized, smooth: true, symbol: 'none',
      lineStyle: { width: 1.9, color: colors[i % colors.length] },
      emphasis: { focus: 'series' },
    })),
  }, true);

  const rows = d.stats.map((s, i) => `<tr data-code="${s.code}">
    <td class="name-cell">${i + 1}. ${esc(s.name)} <span style="color:var(--muted);font-size:11px">${s.code}</span></td>
    <td style="color:${colorFor(s.total_return)}"><b>${pct(s.total_return)}</b></td>
    <td style="color:${colorFor(s.annual_return)}">${pct(s.annual_return)}</td>
    <td style="color:${C().down}">${pct(s.max_drawdown)}</td>
    <td>${pct(s.volatility)}</td>
    <td>${s.sharpe}</td>
    <td>${s.win_rate}%</td>
    <td>${fmt(s.latest_nav)}</td></tr>`).join('');
  $('cmp-stats').innerHTML = `<table class="grid"><thead><tr>
    <th class="nosort">基金</th><th class="nosort">区间收益</th><th class="nosort">年化</th>
    <th class="nosort">最大回撤</th><th class="nosort">年化波动</th><th class="nosort">夏普</th>
    <th class="nosort">上涨占比</th><th class="nosort">最新净值</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
  $$('#cmp-stats tbody tr').forEach(tr => tr.onclick = () => { S.selected = tr.dataset.code; setTab('detail'); });

  // 相关性热力图
  const names = d.names.map(n => n.length > 8 ? n.slice(0, 8) + '…' : n);
  const data = [];
  d.correlation.forEach((row, i) => row.forEach((v, j) => data.push([j, i, v == null ? '-' : v])));
  chart('cmp-corr').setOption({
    animation: false,
    tooltip: { position: 'top', formatter: (p) => `${d.names[p.value[1]]} × ${d.names[p.value[0]]}<br/>相关系数 <b>${p.value[2]}</b>` },
    grid: { left: 88, right: 20, top: 10, bottom: 66 },
    xAxis: { type: 'category', data: names, axisLabel: { fontSize: 9, color: C().muted, rotate: 38 }, splitArea: { show: true } },
    yAxis: { type: 'category', data: names, axisLabel: { fontSize: 9, color: C().muted }, splitArea: { show: true } },
    visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
      itemHeight: 60, textStyle: { fontSize: 9, color: C().muted },
      inRange: { color: ['#16a34a', '#f5f7fa', '#e5453b'] } },
    series: [{ type: 'heatmap', data, label: { show: true, fontSize: 9 },
      emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,.3)' } } }],
  }, true);
}

/* =========================================================
 * TAB 4：新闻中心
 * ======================================================= */
async function loadNews() {
  const p = new URLSearchParams({ sort: S.nw.sort, limit: 40 });
  if (S.nw.q) p.set('q', S.nw.q);
  if (S.nw.sent) p.set('sentiment', S.nw.sent);
  if (S.nw.tag) p.set('tag', S.nw.tag);
  try {
    const nl = await api('/api/news?' + p.toString());
    S.nw.data = nl;
    renderNews();
  } catch (e) { $('news-list').innerHTML = `<div class="empty">加载失败：${esc(e.message)}</div>`; }
}

function renderNews() {
  const nl = S.nw.data; if (!nl) return;
  $('news-note').textContent = `${nl.source_note} · 命中 ${nl.total} 条`;
  $('news-tags').innerHTML = ['<span class="chip ' + (S.nw.tag ? '' : 'on') + '" data-t="">全部主题</span>']
    .concat((nl.tags || []).map(t => `<span class="chip ${S.nw.tag === t ? 'on' : ''}" data-t="${esc(t)}">${esc(t)}</span>`)).join('');
  if (!nl.items.length) {
    $('news-list').innerHTML = '<div class="empty">没有匹配的资讯，试试换个关键词或主题。</div>';
  } else {
    $('news-list').innerHTML = nl.items.map((n, i) => {
      const sCls = n.sentiment > 0.1 ? 'pos' : (n.sentiment < -0.1 ? 'neg' : 'neu');
      const sTxt = n.sentiment > 0.1 ? '利好' : (n.sentiment < -0.1 ? '利空' : '中性');
      const link = n.link && n.link !== '#' ? n.link : null;
      return `<div class="news-item" data-i="${i}">
        <div class="t">${esc(n.title)} ${link ? '<span style="color:var(--muted);font-size:11px">↗</span>' : ''}</div>
        <div class="s">${esc(n.summary || '（无摘要）')}
          ${link ? `<div style="margin-top:5px"><a href="${esc(link)}" target="_blank" rel="noopener">打开原文 / 延伸检索 →</a></div>` : ''}</div>
        <div class="m">
          <span>${esc(n.source)}</span>
          ${n.relevance > 0 ? `<span class="tag rel">相关度 ${n.relevance.toFixed(0)}</span>` : ''}
          <span class="tag ${sCls}">${sTxt} ${n.sentiment >= 0 ? '+' : ''}${n.sentiment.toFixed(1)}</span>
          ${(n.tags || []).map(t => `<span class="tag" data-t="${esc(t)}">#${esc(t)}</span>`).join('')}
          ${n.published ? `<span style="margin-left:auto">${esc(n.published)}</span>` : ''}
        </div></div>`;
    }).join('');
  }
  renderMood(nl);
}

function renderMood(nl) {
  const pos = nl.items.filter(n => n.sentiment > 0.1).length;
  const neg = nl.items.filter(n => n.sentiment < -0.1).length;
  const neu = nl.items.length - pos - neg;
  chart('news-mood').setOption({
    animation: false,
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { fontSize: 10, color: C().muted } },
    series: [{
      type: 'pie', radius: ['42%', '66%'], center: ['50%', '42%'],
      label: { formatter: '{b} {c}', fontSize: 10, color: C().text },
      data: [
        { name: '利好', value: pos, itemStyle: { color: C().up } },
        { name: '中性', value: neu, itemStyle: { color: C().flat } },
        { name: '利空', value: neg, itemStyle: { color: C().down } },
      ],
    }],
  }, true);
}

$('news-list').addEventListener('click', (e) => {
  const tag = e.target.closest('.tag[data-t]');
  if (tag) { e.stopPropagation(); S.nw.tag = tag.dataset.t; loadNews(); return; }
  if (e.target.closest('a')) return;
  const item = e.target.closest('.news-item');
  if (item) item.classList.toggle('open');
});
$('news-tags').addEventListener('click', (e) => {
  const c = e.target.closest('.chip'); if (!c) return;
  S.nw.tag = c.dataset.t; loadNews();
});
$('news-sent').addEventListener('click', (e) => {
  const c = e.target.closest('.chip'); if (!c) return;
  S.nw.sent = c.dataset.s;
  $$('#news-sent .chip').forEach(x => x.classList.toggle('on', x === c));
  loadNews();
});
$('news-sort').onchange = (e) => { S.nw.sort = e.target.value; loadNews(); };
let nwTimer = null;
$('news-q').oninput = (e) => {
  clearTimeout(nwTimer);
  nwTimer = setTimeout(() => { S.nw.q = e.target.value.trim(); loadNews(); }, 350);
};

async function loadSources() {
  try {
    const d = await api('/api/news/sources');
    const all = [...(d.builtin || []).map(s => ({ ...s, builtin: true })), ...(d.custom || [])];
    $('src-list').innerHTML = all.length ? all.map(s => `<div class="src-item">
      <span>${s.type === 'api' ? '🔌' : '📡'}</span>
      <div style="flex:1;min-width:0"><div>${esc(s.name || '未命名')}</div><div class="u">${esc(s.url)}</div></div>
      ${s.builtin ? '<span class="hint">内置</span>' : `<button class="btn sm danger" data-url="${esc(s.url)}">删除</button>`}
    </div>`).join('') : '<div class="hint">尚未配置新闻源，当前展示内置示例资讯。点击右上角「添加 RSS」接入你自己的源。</div>';
  } catch (e) { $('src-list').innerHTML = '<div class="hint">新闻源加载失败</div>'; }
}
$('src-list').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-url]'); if (!b) return;
  try {
    await api('/api/news/sources?url=' + encodeURIComponent(b.dataset.url), { method: 'DELETE' });
    toast('已删除新闻源', 'ok');
    await loadSources(); await loadNews();
  } catch (err) { toast(err.message, 'err'); }
});
$('src-add').onclick = () => {
  modal('添加新闻源', `
    <div class="field" style="margin-bottom:10px"><label>名称</label>
      <input class="inp" id="ns-name" placeholder="如 财联社快讯" /></div>
    <div class="field" style="margin-bottom:10px"><label>RSS / Atom 地址</label>
      <input class="inp" id="ns-url" placeholder="https://example.com/feed.xml" /></div>
    <div class="hint">支持标准 RSS/Atom。添加后系统立即抓取，成功则用真实资讯参与研判。</div>`,
    async () => {
      const name = $('ns-name').value.trim(), url = $('ns-url').value.trim();
      if (!url) return toast('请填写地址', 'err');
      try {
        const r = await api('/api/news/sources', { method: 'POST', body: { name, url, type: 'rss' } });
        closeLayer();
        toast(`已添加，当前资讯 ${r.news_total} 条`, 'ok');
        await loadSources(); await loadNews();
      } catch (err) { toast(err.message, 'err'); }
    }, '添加');
};

/* =========================================================
 * TAB 5：我的持仓
 * ======================================================= */
async function loadPortfolio() {
  try {
    const d = await api('/api/portfolio');
    S.pf.data = d;
    renderPortfolio();
  } catch (e) { $('pf-table').innerHTML = `<div class="empty">加载失败：${esc(e.message)}</div>`; }
}

function renderPortfolio() {
  const d = S.pf.data; if (!d) return;
  const s = d.summary;
  $('pf-kpis').innerHTML = [
    ['持仓基金', s.count],
    ['总市值', '¥' + (s.total_value || 0).toLocaleString()],
    ['总成本', '¥' + (s.total_cost || 0).toLocaleString()],
    ['累计盈亏', (s.total_pnl >= 0 ? '+¥' : '-¥') + Math.abs(s.total_pnl || 0).toLocaleString(), colorFor(s.total_pnl)],
    ['累计收益率', pct(s.total_pnl_pct), colorFor(s.total_pnl_pct)],
    ['今日盈亏', (s.day_pnl >= 0 ? '+¥' : '-¥') + Math.abs(s.day_pnl || 0).toLocaleString(), colorFor(s.day_pnl)],
  ].map(([k, v, col]) => `<div class="kpi"><div class="k">${k}</div><div class="v" style="color:${col || 'inherit'}">${v}</div></div>`).join('');

  if (!d.positions.length) {
    $('pf-table').innerHTML = '<div class="empty">还没有持仓记录。在上方表单选择基金、填入份额与成本净值即可添加；也可以在「监控总览」的卡片上点 ＋ 快速加入。</div>';
  } else {
    $('pf-table').innerHTML = `<table class="grid"><thead><tr>
      <th class="nosort">基金</th><th class="nosort">份额</th><th class="nosort">成本净值</th>
      <th class="nosort">最新净值</th><th class="nosort">市值</th><th class="nosort">盈亏</th>
      <th class="nosort">收益率</th><th class="nosort">今日</th><th class="nosort">权重</th>
      <th class="nosort">建议</th><th class="nosort">操作</th></tr></thead><tbody>
      ${d.positions.map(p => `<tr data-code="${p.code}" data-shares="${p.shares}" data-cost="${p.cost_nav}">
        <td class="name-cell">${esc(p.name)} <span style="color:var(--muted);font-size:11px">${p.code}</span></td>
        <td>${p.shares.toLocaleString()}</td>
        <td>${fmt(p.cost_nav)}</td>
        <td>${fmt(p.latest_nav)}</td>
        <td>¥${(p.value || 0).toLocaleString()}</td>
        <td style="color:${colorFor(p.pnl)}">${p.pnl >= 0 ? '+' : ''}${(p.pnl || 0).toLocaleString()}</td>
        <td style="color:${colorFor(p.pnl_pct)}"><b>${pct(p.pnl_pct)}</b></td>
        <td style="color:${colorFor(p.day_change_pct)}">${pct(p.day_change_pct)}</td>
        <td>${p.weight}%</td>
        <td>${p.advice ? `<span class="advice-chip">${esc(p.advice)}</span>` : '—'}</td>
        <td><button class="btn sm danger" data-act="del">删除</button></td></tr>`).join('')}
      </tbody></table>`;
  }

  // 持仓分布饼图
  chart('pf-pie').setOption({
    animation: false,
    tooltip: { trigger: 'item', formatter: (p) => `${p.name}<br/>市值 ¥${p.value.toLocaleString()}（${p.percent}%）` },
    legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 10, color: C().muted } },
    series: [{ type: 'pie', radius: ['40%', '64%'], center: ['50%', '43%'],
      label: { fontSize: 10, color: C().text, formatter: '{b}\n{d}%' },
      data: d.positions.map(p => ({ name: p.name.length > 10 ? p.name.slice(0, 10) + '…' : p.name, value: p.value || 0 })) }],
  }, true);

  // 建议分布
  const mix = s.advice_mix || {};
  const keys = Object.keys(mix);
  chart('pf-advice').setOption({
    animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v) => v + '%' },
    grid: { left: 60, right: 24, top: 14, bottom: 24 },
    xAxis: { type: 'value', axisLabel: { formatter: '{value}%', fontSize: 10, color: C().muted }, splitLine: { lineStyle: { color: C().split } } },
    yAxis: { type: 'category', data: keys, axisLabel: { fontSize: 11, color: C().text }, axisLine: { lineStyle: { color: C().split } } },
    series: [{ type: 'bar', data: keys.map(k => ({
      value: mix[k],
      itemStyle: { color: k.includes('加仓') || k.includes('买入') ? C().up : (k.includes('减仓') || k.includes('卖出') ? C().down : C().accent) },
    })), barWidth: '52%', label: { show: true, position: 'right', formatter: '{c}%', fontSize: 10, color: C().muted } }],
  }, true);
}

$('pf-table').addEventListener('click', async (e) => {
  const tr = e.target.closest('tr[data-code]'); if (!tr) return;
  const code = tr.dataset.code;
  if (e.target.closest('[data-act="del"]')) {
    e.stopPropagation();
    modal('删除持仓', `确定删除 <b>${code}</b> 的持仓记录？`, async () => {
      try {
        S.pf.data = await api(`/api/portfolio/${code}`, { method: 'DELETE' });
        closeLayer(); renderPortfolio(); loadFunds(true);
        toast('已删除持仓', 'ok');
      } catch (err) { toast(err.message, 'err'); }
    }, '删除');
    return;
  }
  // 点击行 -> 载入表单编辑
  if (!$$('#pf-code option').some(o => o.value === code)) {
    $('pf-code').insertAdjacentHTML('beforeend', `<option value="${code}">${code}</option>`);
  }
  $('pf-code').value = code;
  $('pf-shares').value = tr.dataset.shares;
  $('pf-cost').value = tr.dataset.cost;
  $('pf-hint').textContent = `正在编辑 ${code}，修改后点「保存持仓」`;
});

$('pf-save').onclick = async () => {
  const code = $('pf-code').value;
  const shares = parseFloat($('pf-shares').value);
  const cost = parseFloat($('pf-cost').value);
  if (!code) return toast('请选择基金', 'err');
  if (!shares || shares <= 0) return toast('请输入有效份额', 'err');
  if (!cost || cost <= 0) return toast('请输入有效成本净值', 'err');
  try {
    S.pf.data = await api('/api/portfolio', { method: 'POST', body: { code, shares, cost_nav: cost } });
    renderPortfolio();
    $('pf-hint').textContent = '';
    $('pf-shares').value = ''; $('pf-cost').value = '';
    toast('持仓已保存', 'ok');
    loadFunds(true);
  } catch (e) { toast(e.message, 'err'); }
};

function openHoldingModal(f) {
  const nav = f.latest_nav || (S.dt.data && S.dt.data.history?.slice(-1)[0]?.nav) || '';
  modal(`加入持仓 · ${esc(f.name)}`, `
    <div class="form-row">
      <div class="field" style="flex:1"><label>持有份额</label>
        <input class="inp" id="h-shares" type="number" step="0.01" placeholder="如 1000" /></div>
      <div class="field" style="flex:1"><label>成本净值</label>
        <input class="inp" id="h-cost" type="number" step="0.0001" value="${nav}" /></div>
    </div>
    <div class="hint" style="margin-top:8px">最新净值 ${fmt(f.latest_nav)}，默认按最新净值作为成本，可自行修改。</div>`,
    async () => {
      const shares = parseFloat($('h-shares').value), cost = parseFloat($('h-cost').value);
      if (!shares || shares <= 0) return toast('请输入有效份额', 'err');
      if (!cost || cost <= 0) return toast('请输入有效成本净值', 'err');
      try {
        S.pf.data = await api('/api/portfolio', { method: 'POST', body: { code: f.code, shares, cost_nav: cost, name: f.name } });
        closeLayer();
        toast(`已加入持仓：${f.name}`, 'ok');
        await loadFunds(true);
        if (S.tab === 'portfolio') renderPortfolio();
      } catch (e) { toast(e.message, 'err'); }
    }, '加入持仓');
  setTimeout(() => $('h-shares') && $('h-shares').focus(), 50);
}

/* =========================================================
 * TAB 6：策略回测
 * ======================================================= */
async function runBacktest() {
  const code = $('bt-code').value;
  if (!code) return toast('请选择基金', 'err');
  const p = new URLSearchParams({
    strategy: $('bt-strategy').value,
    short: $('bt-short').value || 5,
    long: $('bt-long').value || 20,
    days: $('bt-days').value,
    fee_bps: $('bt-fee').value || 15,
  });
  $('bt-kpis').innerHTML = '<div class="loading">回测计算中</div>';
  try {
    const d = await api(`/api/backtest/${code}?${p.toString()}`);
    S.bt.data = d;
    renderBacktest();
    toast(`回测完成：${d.strategy_name} 收益 ${pct(d.stats.total_return)}`, 'ok');
  } catch (e) {
    $('bt-kpis').innerHTML = `<div class="empty">回测失败：${esc(e.message)}</div>`;
  }
}

function renderBacktest() {
  const d = S.bt.data; if (!d) return;
  const st = d.stats, bm = d.benchmark_stats;
  $('bt-kpis').innerHTML = [
    ['策略收益', pct(st.total_return), colorFor(st.total_return)],
    ['基准收益', pct(bm.total_return), colorFor(bm.total_return)],
    ['超额收益', pct(st.excess_return), colorFor(st.excess_return)],
    ['年化收益', pct(st.annual_return), colorFor(st.annual_return)],
    ['最大回撤', pct(st.max_drawdown), C().down],
    ['夏普比率', st.sharpe, st.sharpe > 1 ? C().up : ''],
    ['交易次数', st.trade_count],
    ['交易胜率', st.trade_win_rate + '%', st.trade_win_rate >= 50 ? C().up : C().down],
    ['持仓时间占比', st.holding_ratio + '%'],
  ].map(([k, v, col]) => `<div class="kpi"><div class="k">${k}</div><div class="v" style="color:${col || 'inherit'};font-size:16px">${v}</div></div>`).join('');

  const buyPts = d.marks.filter(m => m.type === 'buy');
  const sellPts = d.marks.filter(m => m.type === 'sell');
  const idx = (dt) => d.dates.indexOf(dt);
  chart('bt-chart').setOption({
    animation: false,
    tooltip: { ...tipBase(), valueFormatter: (v) => v == null ? '—' : (v * 100 - 100).toFixed(2) + '%' },
    legend: { top: 0, right: 0, textStyle: { fontSize: 11, color: C().muted } },
    grid: { left: 54, right: 18, top: 32, bottom: 42 },
    xAxis: { type: 'category', data: d.dates, boundaryGap: false, ...axisBase() },
    yAxis: { type: 'value', scale: true, axisLabel: { formatter: (v) => ((v - 1) * 100).toFixed(0) + '%', fontSize: 10, color: C().muted },
             axisLine: { lineStyle: { color: C().split } }, splitLine: { lineStyle: { color: C().split } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 15, bottom: 6, borderColor: C().split, textStyle: { fontSize: 9, color: C().muted } }],
    series: [
      { name: d.strategy_name, type: 'line', data: d.equity, smooth: true, symbol: 'none',
        lineStyle: { width: 2.2, color: C().accent },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: theme === 'dark' ? 'rgba(77,134,255,.24)' : 'rgba(47,111,237,.16)' },
          { offset: 1, color: 'rgba(47,111,237,0)' }]) },
        markPoint: { symbolSize: 34, data: [
          ...buyPts.map(m => ({ name: '买入', coord: [idx(m.date), d.equity[idx(m.date)]], value: 'B',
            itemStyle: { color: C().up }, label: { fontSize: 9, color: '#fff' } })),
          ...sellPts.map(m => ({ name: '卖出', coord: [idx(m.date), d.equity[idx(m.date)]], value: 'S',
            itemStyle: { color: C().down }, label: { fontSize: 9, color: '#fff' } })),
        ] } },
      { name: '买入持有(基准)', type: 'line', data: d.benchmark, smooth: true, symbol: 'none',
        lineStyle: { width: 1.5, color: C().muted, type: 'dashed' } },
    ],
  }, true);

  const tr = d.trades || [];
  $('bt-trades').innerHTML = tr.length ? `<table class="grid"><thead><tr>
    <th class="nosort">#</th><th class="nosort">买入日</th><th class="nosort">买入净值</th>
    <th class="nosort">卖出日</th><th class="nosort">卖出净值</th><th class="nosort">收益</th><th class="nosort">结果</th></tr></thead>
    <tbody>${tr.map((t, i) => `<tr>
      <td class="name-cell">${i + 1}</td><td>${t.entry_date}</td><td>${fmt(t.entry_nav)}</td>
      <td>${t.exit_date}</td><td>${fmt(t.exit_nav)}</td>
      <td style="color:${colorFor(t.return_pct)}"><b>${pct(t.return_pct)}</b></td>
      <td>${t.win ? '<span class="badge up">盈利</span>' : '<span class="badge down">亏损</span>'}</td></tr>`).join('')}
    </tbody></table>` : '<div class="empty">该参数下没有产生交易（信号从未触发）。试试更短的均线周期。</div>';
}

$('bt-run').onclick = runBacktest;
$('bt-strategy').onchange = (e) => {
  const isMom = e.target.value === 'momentum';
  const isBH = e.target.value === 'buy_hold';
  $('bt-short').disabled = isBH;
  $('bt-long').disabled = isBH || isMom;
  $('bt-short').parentElement.querySelector('label').textContent = isMom ? '回看周期' : '短周期';
};

/* ---------------- 定投回测 ---------------- */
function runDca() {
  const code = $('dca-code').value || ($('bt-code') && $('bt-code').value) || (S.funds[0] && S.funds[0].code);
  if (!code) return toast('请先添加基金', 'err');
  const p = new URLSearchParams({
    strategy: $('dca-strategy').value,
    freq: $('dca-freq').value,
    amount: $('dca-amount').value,
    fee_bps: $('dca-fee').value,
    days: $('dca-days').value,
  });
  $('dca-kpis').innerHTML = '<div class="loading">定投回测计算</div>';
  api(`/api/dca/${code}?${p.toString()}`).then(d => {
    S.dca.data = d;
    renderDca();
    toast(`定投回测完成：${d.strategy_name} 收益 ${pct(d.total_return_pct)}`, 'ok');
  }).catch(e => { $('dca-kpis').innerHTML = `<div class="empty">定投回测失败：${esc(e.message)}</div>`; });
}

function renderDca() {
  const d = S.dca.data; if (!d) return;
  $('dca-kpis').innerHTML = [
    ['策略', d.strategy_name],
    ['定投期数', d.periods],
    ['累计本金', '¥' + (d.principal || 0).toLocaleString()],
    ['期末市值', '¥' + (d.final_value || 0).toLocaleString()],
    ['总收益率', pct(d.total_return_pct), colorFor(d.total_return_pct)],
    ['资金加权年化(XIRR)', pct(d.xirr_pct), ''],
    ['区间', `${d.first_date} ~ ${d.last_date}`],
  ].map(([k, v, col]) => `<div class="kpi"><div class="k">${k}</div><div class="v" style="color:${col || 'inherit'};font-size:15px">${v}</div></div>`).join('');

  chart('dca-chart').setOption({
    animation: false,
    tooltip: { ...tipBase(), valueFormatter: (v) => v == null ? '—' : '¥' + Number(v).toLocaleString() },
    legend: { top: 0, right: 0, textStyle: { fontSize: 11, color: C().muted } },
    grid: { left: 62, right: 18, top: 32, bottom: 42 },
    xAxis: { type: 'category', data: d.dates, boundaryGap: false, ...axisBase() },
    yAxis: [
      { type: 'value', scale: true, name: '市值/成本', axisLabel: { formatter: (v) => '¥' + (v / 1000).toFixed(0) + 'k', fontSize: 10, color: C().muted }, axisLine: { lineStyle: { color: C().split } }, splitLine: { lineStyle: { color: C().split } } },
      { type: 'value', name: '净值', scale: true, position: 'right', axisLabel: { fontSize: 10, color: C().muted }, axisLine: { lineStyle: { color: C().split } }, splitLine: { show: false } },
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 15, bottom: 6, borderColor: C().split, textStyle: { fontSize: 9, color: C().muted } }],
    series: [
      { name: '定投市值', type: 'line', data: d.value_series, smooth: true, symbol: 'none',
        lineStyle: { width: 2.2, color: C().accent },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: theme === 'dark' ? 'rgba(77,134,255,.24)' : 'rgba(47,111,237,.16)' },
          { offset: 1, color: 'rgba(47,111,237,0)' }]) } },
      { name: '累计投入成本', type: 'line', data: d.cost_series, smooth: true, symbol: 'none',
        lineStyle: { width: 1.6, color: C().muted, type: 'dashed' } },
      { name: '单位净值', type: 'line', yAxisIndex: 1, data: d.nav_series, smooth: true, symbol: 'none',
        lineStyle: { width: 1.2, color: C().up, opacity: 0.7 } },
    ],
  }, true);
}
$('dca-run').onclick = runDca;

/* ---------------- 组合再平衡 ---------------- */
function runRebalance() {
  api(`/api/rebalance?method=${S.reb.method}`).then(d => {
    S.reb.data = d;
    renderRebalance();
  }).catch(e => {
    $('pf-reb-table').innerHTML = `<div class="empty">再平衡失败：${esc(e.message)}</div>`;
    $('pf-reb-note').textContent = '';
  });
}

function renderRebalance() {
  const d = S.reb.data; if (!d) return;
  $('pf-reb-note').textContent = d.note || '';
  const rows = d.positions.map(p => `<tr>
    <td class="name-cell">${esc(p.name || p.code)} <span style="color:var(--muted);font-size:11px">${p.code}</span></td>
    <td>${p.current_weight}%</td>
    <td style="color:${C().accent}"><b>${p.target_weight}%</b></td>
    <td>${p.delta_pct}%</td>
    <td style="color:${colorFor(p.delta_value)}">${p.delta_value >= 0 ? '+' : ''}¥${Math.abs(p.delta_value).toLocaleString()}</td>
    <td>${p.action === '加仓' ? '<span class="badge up">加仓</span>' : p.action === '减仓' ? '<span class="badge down">减仓</span>' : '<span class="badge flat">持有</span>'}</td>
    <td>${p.suggested_shares >= 0 ? '+' : ''}${(p.suggested_shares || 0).toLocaleString()} 份</td>
  </tr>`).join('');
  $('pf-reb-table').innerHTML = `<table class="grid"><thead><tr>
    <th class="nosort">基金</th><th class="nosort">当前权重</th><th class="nosort">目标权重</th>
    <th class="nosort">权重变动</th><th class="nosort">调仓金额</th><th class="nosort">动作</th><th class="nosort">建议份额</th>
    </tr></thead><tbody>${rows || '<tr><td colspan="7" class="empty">暂无持仓，请先在上方添加持仓</td></tr>'}</tbody></table>`;

  const cats = d.positions.map(p => (p.name && p.name.length > 8 ? p.name.slice(0, 8) + '…' : (p.name || p.code)));
  chart('pf-reb-chart').setOption({
    animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v) => v + '%' },
    legend: { top: 0, textStyle: { fontSize: 10, color: C().muted } },
    grid: { left: 48, right: 16, top: 28, bottom: 20 },
    xAxis: { type: 'category', data: cats, axisLabel: { fontSize: 10, color: C().text, interval: 0 }, axisLine: { lineStyle: { color: C().split } } },
    yAxis: { type: 'value', axisLabel: { formatter: '{value}%', fontSize: 10, color: C().muted }, splitLine: { lineStyle: { color: C().split } } },
    series: [
      { name: '当前权重', type: 'bar', data: d.positions.map(p => p.current_weight), itemStyle: { color: C().muted } },
      { name: '目标权重', type: 'bar', data: d.positions.map(p => p.target_weight), itemStyle: { color: C().accent } },
    ],
  }, true);
}
$('pf-reb-run').onclick = runRebalance;
$('pf-reb-method').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  S.reb.method = b.dataset.m;
  $$('#pf-reb-method button').forEach(x => x.classList.toggle('on', x === b));
  runRebalance();
});
document.querySelector('#tab-backtest .toolbar').addEventListener('click', (e) => {
  const c = e.target.closest('.chip[data-preset]'); if (!c) return;
  const [s, l] = c.dataset.preset.split(',');
  $('bt-short').value = s; $('bt-long').value = l;
  $('bt-strategy').value = 'ma_cross';
  $('bt-long').disabled = false;
  runBacktest();
});

/* =========================================================
 * 基金搜索 & 添加
 * ======================================================= */
let sgTimer = null, sgList = [], sgIdx = -1;
$('fund-search').addEventListener('input', (e) => {
  const q = e.target.value.trim();
  clearTimeout(sgTimer);
  if (!q) { $('suggest').classList.remove('show'); return; }
  sgTimer = setTimeout(async () => {
    try {
      const d = await api('/api/search?q=' + encodeURIComponent(q) + '&limit=14');
      sgList = d.results; sgIdx = -1;
      $('suggest').innerHTML = d.results.length ? d.results.map((r, i) => `
        <div class="suggest-item" data-i="${i}">
          <span class="s-code">${r.code}</span>
          <span class="s-name">${esc(r.name)}</span>
          <span class="s-type">${esc(r.type || '')}</span>
          ${r.added ? '<span class="s-add">已在自选</span>' : '<span class="s-add">＋ 添加</span>'}
        </div>`).join('') : `<div class="suggest-empty">未找到「${esc(q)}」，可试基金代码、中文名或拼音缩写</div>`;
      $('suggest').classList.add('show');
    } catch (err) { /* 静默 */ }
  }, 260);
});
$('fund-search').addEventListener('keydown', (e) => {
  const box = $('suggest');
  if (!box.classList.contains('show')) return;
  const items = $$('.suggest-item', box);
  if (e.key === 'ArrowDown') { e.preventDefault(); sgIdx = Math.min(sgIdx + 1, items.length - 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); sgIdx = Math.max(sgIdx - 1, 0); }
  else if (e.key === 'Enter') { e.preventDefault(); if (items[sgIdx]) items[sgIdx].click(); else if (items[0]) items[0].click(); return; }
  else if (e.key === 'Escape') { box.classList.remove('show'); return; }
  items.forEach((el, i) => el.classList.toggle('hl', i === sgIdx));
});
$('suggest').addEventListener('click', async (e) => {
  const it = e.target.closest('.suggest-item'); if (!it) return;
  const r = sgList[+it.dataset.i]; if (!r) return;
  $('suggest').classList.remove('show');
  $('fund-search').value = '';
  if (r.added) { S.selected = r.code; setTab('detail'); return; }
  toast(`正在添加「${r.name}」…`);
  try {
    const res = await api('/api/funds', { method: 'POST', body: { code: r.code } });
    await loadFunds(true);
    S.selected = r.code;
    toast(`已添加「${r.name}」· ${res.data_source === 'real' ? '真实净值' : '模拟数据'} ${res.points} 条`, 'ok');
    setTab('overview');
  } catch (err) { toast(err.message, 'err'); }
});
document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-wrap')) $('suggest').classList.remove('show');
});

$('pill-reset').onclick = () => {
  modal('恢复默认自选', '将自选列表恢复为系统默认的 8 只 CPO/科技基金（含两只重点关注）。你手动添加的基金会被移除，持仓记录保留。', async () => {
    try {
      await api('/api/watchlist/reset', { method: 'POST' });
      closeLayer(); S.selected = null;
      await loadFunds(true);
      toast('已恢复默认自选', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }, '恢复默认');
};

/* =========================================================
 * 价格提醒（本地保存）
 * ======================================================= */
function saveAlerts() { localStorage.setItem('qts_alerts', JSON.stringify(S.alerts)); }

function checkAlerts() {
  S.fired = [];
  S.alerts.forEach(a => {
    const f = S.funds.find(x => x.code === a.code);
    if (!f) return;
    const day = f.day_change_pct, nav = f.latest_nav;
    let hit = false;
    if (a.type === 'up' && day != null) hit = day >= a.value;
    else if (a.type === 'down' && day != null) hit = day <= -Math.abs(a.value);
    else if (a.type === 'above' && nav != null) hit = nav >= a.value;
    else if (a.type === 'below' && nav != null) hit = nav <= a.value;
    if (hit) S.fired.push({ ...a, name: f.name, cur: a.type === 'up' || a.type === 'down' ? pct(day) : fmt(nav) });
  });
  const cnt = $('alert-count');
  cnt.textContent = S.fired.length;
  cnt.classList.toggle('show', S.fired.length > 0);
  if (S.fired.length && !S._alertToastAt) {
    S._alertToastAt = Date.now();
    toast(`🔔 ${S.fired.length} 个提醒被触发：${S.fired[0].name}`, 'err');
  } else if (!S.fired.length) S._alertToastAt = null;
}

const ALERT_TEXT = { up: '当日涨幅 ≥', down: '当日跌幅 ≥', above: '净值 ≥', below: '净值 ≤' };
function alertLabel(a) {
  const unit = (a.type === 'up' || a.type === 'down') ? '%' : '';
  return `${ALERT_TEXT[a.type]} ${a.value}${unit}`;
}

$('btn-alerts').onclick = () => {
  const rows = S.alerts.map((a, i) => {
    const f = S.funds.find(x => x.code === a.code);
    const fired = S.fired.some(x => x.id === a.id);
    return `<div class="alert-item ${fired ? 'fired' : ''}">
      <div class="txt"><b>${esc(f ? f.name : a.code)}</b><br/>
        <span class="hint">${alertLabel(a)} ${fired ? '· 已触发 ✅' : ''}</span></div>
      <button class="btn sm danger" data-del="${i}">删除</button></div>`;
  }).join('');
  $('layer').innerHTML = `<div class="mask" id="mask"><div class="drawer" onclick="event.stopPropagation()">
    <h3>🔔 价格提醒 <button class="btn sm" id="al-close" style="margin-left:auto">关闭</button></h3>
    <div class="form-row" style="margin-bottom:12px">
      <div class="field" style="min-width:100%"><label>基金</label>
        <select class="sel" id="al-code">${S.funds.map(f => `<option value="${f.code}">${esc(f.name)}</option>`).join('')}</select></div>
      <div class="field" style="flex:1"><label>条件</label>
        <select class="sel" id="al-type">
          <option value="up">当日涨幅 ≥</option><option value="down">当日跌幅 ≥</option>
          <option value="above">净值 ≥</option><option value="below">净值 ≤</option></select></div>
      <div class="field" style="width:88px"><label>阈值</label>
        <input class="inp" id="al-val" type="number" step="0.01" value="2" /></div>
      <button class="btn primary" id="al-add">添加提醒</button>
    </div>
    <div>${rows || '<div class="hint">还没有提醒。设置后，每次刷新都会自动检查，触发时会提示你。</div>'}</div>
  </div></div>`;
  $('mask').onclick = (e) => { if (e.target.id === 'mask') closeLayer(); };
  $('al-close').onclick = closeLayer;
  $('al-add').onclick = () => {
    const code = $('al-code').value, type = $('al-type').value, value = parseFloat($('al-val').value);
    if (!code || isNaN(value)) return toast('请填写完整', 'err');
    S.alerts.push({ id: Date.now(), code, type, value });
    saveAlerts(); checkAlerts(); toast('提醒已添加', 'ok');
    $('btn-alerts').click();
  };
  $$('#layer [data-del]').forEach(b => b.onclick = () => {
    S.alerts.splice(+b.dataset.del, 1);
    saveAlerts(); checkAlerts(); $('btn-alerts').click();
  });
};

function openAlertModal(f) {
  modal(`价格提醒 · ${esc(f.name)}`, `
    <div class="form-row">
      <div class="field" style="flex:1"><label>条件</label>
        <select class="sel" id="am-type">
          <option value="up">当日涨幅 ≥</option><option value="down">当日跌幅 ≥</option>
          <option value="above">净值 ≥</option><option value="below">净值 ≤</option></select></div>
      <div class="field" style="width:100px"><label>阈值</label>
        <input class="inp" id="am-val" type="number" step="0.01" value="2" /></div>
    </div>
    <div class="hint" style="margin-top:8px">当前净值 ${fmt(f.latest_nav)}，当日 ${pct(f.day_change_pct)}。提醒保存在本地浏览器。</div>`,
    () => {
      const type = $('am-type').value, value = parseFloat($('am-val').value);
      if (isNaN(value)) return toast('请输入阈值', 'err');
      S.alerts.push({ id: Date.now(), code: f.code, type, value });
      saveAlerts(); checkAlerts(); closeLayer();
      toast('提醒已添加', 'ok');
    }, '保存提醒');
}

/* =========================================================
 * 标签页 / 刷新 / 主题 / 快捷键
 * ======================================================= */
function setTab(name) {
  S.tab = name;
  $$('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name === 'detail') loadDetail();
  if (name === 'compare') { syncFundSelectors(); if (!S.cmp.data) runCompare(); else renderCompare(); }
  if (name === 'news') { loadNews(); loadSources(); }
  if (name === 'portfolio') { loadPortfolio(); runRebalance(); }
  if (name === 'backtest') { if (!S.bt.data) runBacktest(); else renderBacktest(); if (!S.dca.data) runDca(); else renderDca(); }
  if (name === 'overview') {
    if (!S.trend.loaded) loadTrend();
    else setTimeout(() => { const c = chart('ov-trend-chart'); if (c) c.resize(); }, 60);
  }
  setTimeout(() => Object.values(CH).forEach(c => c.resize()), 60);
}
$('tabs').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  setTab(b.dataset.tab);
});

async function refreshAll(silent) {
  try {
    await loadFunds(silent);
    if (S.tab === 'detail') await loadDetail();
    if (S.tab === 'news') await loadNews();
    if (S.tab === 'portfolio') await loadPortfolio();
  } catch (e) { toast('刷新出错：' + e.message, 'err'); }
}

$('btn-refresh').onclick = async () => {
  const b = $('btn-refresh');
  b.disabled = true; b.textContent = '刷新中…';
  try {
    const r = await api('/api/refresh', { method: 'POST' });
    await refreshAll(true);
    toast(`已刷新：${r.funds} 只基金 · ${r.news} 条资讯`, 'ok');
  } catch (e) { toast('刷新失败：' + e.message, 'err'); }
  b.disabled = false; b.textContent = '立即刷新';
};

function startTimer() {
  clearInterval(S.timer);
  if (S.interval > 0) S.timer = setInterval(() => refreshAll(true), S.interval);
}
$('interval-select').onchange = (e) => {
  S.interval = +e.target.value;
  startTimer();
  toast(S.interval ? `自动刷新：每 ${S.interval / 1000} 秒` : '已切换为手动刷新', 'ok');
};

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme);
  $('btn-theme').textContent = theme === 'dark' ? '☀️' : '🌙';
}
$('btn-theme').onclick = () => {
  theme = theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('qts_theme', theme);
  applyTheme();
  disposeCharts();
  renderOverview();
  if (S.tab === 'detail' && S.dt.data) { renderDetailChart(); renderDetailKpis(); }
  if (S.tab === 'compare' && S.cmp.data) renderCompare();
  if (S.tab === 'news' && S.nw.data) renderNews();
  if (S.tab === 'portfolio' && S.pf.data) renderPortfolio();
  if (S.tab === 'backtest' && S.bt.data) renderBacktest();
  if (S.tab === 'overview' && S.trend.data) renderTrendChart(S.trend.data);
};

document.addEventListener('keydown', (e) => {
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
  const tabs = ['overview', 'detail', 'compare', 'news', 'portfolio', 'backtest'];
  if (e.key >= '1' && e.key <= '6') setTab(tabs[+e.key - 1]);
  else if (e.key.toLowerCase() === 'r') $('btn-refresh').click();
  else if (e.key === '/') { e.preventDefault(); $('fund-search').focus(); }
  else if (e.key === 'Escape') closeLayer();
});

window.addEventListener('resize', () => Object.values(CH).forEach(c => c.resize()));

/* ---------------- 启动 ---------------- */
(async function init() {
  applyTheme();
  wireTrend();
  await loadHealth();
  await loadFunds();
  startTimer();
  toast('系统就绪：点击卡片查看详情，顶部搜索可添加任意基金', 'ok');
})();
