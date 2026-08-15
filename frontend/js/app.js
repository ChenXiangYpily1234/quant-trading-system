const UP = '#e5453b', DOWN = '#1fa971', FLAT = '#8a94a6', ACCENT = '#2f6fed';
let autoRefresh = true;
let selectedCode = null;
let timer = null;
let chart = null;

const $ = (id) => document.getElementById(id);
function colorFor(v) { return v > 0 ? UP : (v < 0 ? DOWN : FLAT); }
function fmt(v, d = 4) { return v == null ? '—' : Number(v).toFixed(d); }
function pct(v) { return v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%'; }
function dirBadge(dir) {
  if (dir === 'up') return '<span class="badge up">看多 ↗</span>';
  if (dir === 'down') return '<span class="badge down">看空 ↘</span>';
  return '<span class="badge flat">震荡 →</span>';
}
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error('请求失败 ' + path);
  return r.json();
}

async function loadHealth() {
  try {
    const h = await api('/api/health');
    $('pill-llm').textContent = '大模型：' + (h.llm_enabled ? '已接入' : '规则引擎');
    $('pill-llm').className = 'pill ' + (h.llm_enabled ? 'real' : 'sim');
    $('pill-source').textContent = `监控 ${h.funds_monitored} 只基金`;
  } catch (e) { $('pill-llm').textContent = '大模型：离线'; }
}

async function loadFunds() {
  const funds = await api('/api/funds');
  funds.sort((a, b) => (b.focus ? 1 : 0) - (a.focus ? 1 : 0));  // 重点基金置顶
  const grid = $('fund-grid');
  grid.innerHTML = '';
  let anyReal = false, anySim = false;
  funds.forEach(f => {
    if (f.data_source === 'real') anyReal = true; else anySim = true;
    const card = document.createElement('div');
    card.className = 'fund-card' + (f.code === selectedCode ? ' active' : '') + (f.focus ? ' focus' : '');
    if (f.focus) { card.style.borderColor = '#e5453b'; card.style.boxShadow = '0 0 0 1px rgba(229,69,59,.35)'; }
    const estCls = f.estimate_change_pct > 0 ? UP : (f.estimate_change_pct < 0 ? DOWN : FLAT);
    card.innerHTML = `
      <div class="cat">${f.category}${f.focus ? ' <span class="focus-badge">★ 重点</span>' : ''}</div>
      <div class="name">${f.name}</div>
      <div class="code"><span class="dot ${f.data_source === 'real' ? 'real' : 'sim'}"></span> ${f.code}</div>
      <div class="nav-row">
        <span class="nav">${fmt(f.latest_nav)}</span>
        <span class="chg" style="color:${colorFor(f.day_change_pct)}">${pct(f.day_change_pct)}</span>
      </div>
      <div class="est">盘中模拟估值 ${fmt(f.estimate_nav)} <span style="color:${estCls}">${pct(f.estimate_change_pct)}</span></div>
      <div class="foot">
        ${dirBadge(f.direction)}
        <span class="advice-chip">${f.advice}</span>
        <span class="conf" style="margin-left:auto">置信 ${Math.round((f.confidence||0)*100)}%</span>
      </div>`;
    card.onclick = () => { selectedCode = f.code; loadDetail(); loadFunds(); };
    grid.appendChild(card);
  });
  const srcPill = $('pill-source');
  if (anyReal && !anySim) srcPill.textContent = '数据源：实时';
  else if (!anyReal && anySim) srcPill.textContent = '数据源：模拟(降级)';
  else srcPill.textContent = '数据源：实时+模拟';
  srcPill.className = 'pill ' + (anySim ? 'sim' : 'real');
  $('pill-update').textContent = '更新：' + new Date().toLocaleTimeString('zh-CN');
}

async function loadNews() {
  const nl = await api('/api/news');
  const box = $('news-list');
  let html = `<div style="font-size:11px;color:var(--muted);margin-bottom:8px">${nl.source_note} · 共${nl.total}条</div>`;
  nl.items.slice(0, 25).forEach(n => {
    const sCls = n.sentiment > 0.1 ? 'pos' : (n.sentiment < -0.1 ? 'neg' : 'neu');
    const sTxt = n.sentiment > 0.1 ? '利好' : (n.sentiment < -0.1 ? '利空' : '中性');
    html += `<div class="news-item">
      <div class="t">${n.title}</div>
      <div class="m">
        <span>${n.source}</span>
        ${n.relevance > 0 ? `<span class="tag rel">相关度 ${n.relevance.toFixed(0)}</span>` : ''}
        <span class="tag ${sCls}">${sTxt} ${n.sentiment>=0?'+':''}${n.sentiment.toFixed(1)}</span>
        ${n.published ? `<span>${n.published}</span>` : ''}
      </div></div>`;
  });
  box.innerHTML = html;
}

async function loadDetail() {
  if (!selectedCode) {
    $('detail-wrap').innerHTML = '';
    return;
  }
  const d = await api('/api/funds/' + selectedCode);
  const rec = d.recommendation;
  const ind = d.prediction.indicators;
  const wrap = $('detail-wrap');
  wrap.innerHTML = `
    <div class="detail">
      <div class="dhead">
        <h2>${d.name}</h2>
        <span class="cat">${d.category}</span>
        ${d.focus ? '<span class="focus-badge">★ 重点</span>' : ''}
        <span class="code">${d.code}</span>
        <span class="meta">数据源：${d.data_source === 'real' ? '实时净值' : '模拟数据'}</span>
        <span class="meta">最新净值日：${d.latest_date || '—'}</span>
      </div>
      <div id="chart" class="chart"></div>
      <div class="kpis">
        <div class="kpi"><div class="k">近5日动量</div><div class="v" style="color:${colorFor(ind.momentum5)}">${pct(ind.momentum5)}</div></div>
        <div class="kpi"><div class="k">近20日动量</div><div class="v" style="color:${colorFor(ind.momentum20)}">${pct(ind.momentum20)}</div></div>
        <div class="kpi"><div class="k">RSI(14)</div><div class="v">${ind.rsi}</div></div>
        <div class="kpi"><div class="k">日波动率</div><div class="v">${ind.volatility}%</div></div>
      </div>
      <div class="analysis">
        <div class="row"><span class="label">研判引擎</span><span class="val"><span class="engine-tag">${rec.engine === 'llm' ? '大模型 LLM' : '规则引擎(内置)'}</span></span></div>
        <div class="row"><span class="label">走势预测</span><span class="val">${rec.trend_prediction} ${rec.predicted_nav ? `· 目标净值 <b>${fmt(rec.predicted_nav)}</b> (${pct(rec.predicted_change_pct)})` : ''} · 置信 ${Math.round((rec.confidence||0)*100)}%</span></div>
        <div class="row"><span class="label">操作建议</span><span class="val"><b style="color:${ACCENT}">${rec.advice}</b> ｜ 仓位动作：<b>${rec.position_action}</b> ｜ 风险等级：<b>${rec.risk_level}</b></span></div>
        <div class="row"><span class="label">分析依据</span><span class="val">${rec.reasoning}</span></div>
        ${rec.key_news && rec.key_news.length ? `<div class="row"><span class="label">关键新闻</span><span class="val">${rec.key_news.map(x=>'· '+x).join('<br>')}</span></div>` : ''}
      </div>
    </div>`;
  renderChart(d);
}

function renderChart(d) {
  if (!chart) chart = echarts.init($('chart'));
  const hist = d.history;
  const dates = hist.map(h => h.date);
  const nav = hist.map(h => h.nav);
  const ma5 = d.ma5;
  const ma20 = d.ma20;
  const pred = d.prediction;
  // 拼接预测段
  const allDates = dates.concat(pred.future_dates);
  const nHist = dates.length;
  const predLine = Array(nHist).fill(null);
  predLine[nHist - 1] = nav[nHist - 1];
  pred.forEach(v => predLine.push(v));
  const bandLow = Array(nHist).fill(null);
  const bandDelta = Array(nHist).fill(null);
  bandLow[nHist - 1] = nav[nHist - 1];
  pred.future_lower.forEach(v => bandLow.push(v));
  pred.future_upper.forEach((v, i) => bandDelta.push(+(v - pred.future_lower[i]).toFixed(4)));
  const navExt = nav.concat(Array(pred.future_dates.length).fill(null));
  const ma5Ext = ma5.concat(Array(pred.future_dates.length).fill(null));
  const ma20Ext = ma20.concat(Array(pred.future_dates.length).fill(null));

  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['单位净值', 'MA5', 'MA20', '预测', '置信区间'], top: 0, right: 0, textStyle: { fontSize: 11 } },
    grid: { left: 48, right: 16, top: 36, bottom: 30 },
    xAxis: { type: 'category', data: allDates, axisLabel: { fontSize: 10, color: '#8a94a6' } },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: { fontSize: 10, color: '#8a94a6' } },
    series: [
      { name: '单位净值', type: 'line', data: navExt, smooth: true, symbol: 'none', lineStyle: { width: 2.4, color: ACCENT },
        areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(47,111,237,.18)'},{offset:1,color:'rgba(47,111,237,0)'}]) }, z: 5 },
      { name: 'MA5', type: 'line', data: ma5Ext, smooth: true, symbol: 'none', lineStyle: { width: 1.2, color: '#f5a623', type: 'dashed' } },
      { name: 'MA20', type: 'line', data: ma20Ext, smooth: true, symbol: 'none', lineStyle: { width: 1.2, color: '#9b59b6', type: 'dashed' } },
      { name: '置信区间', type: 'line', data: bandLow, stack: 'conf', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, z: 1 },
      { name: '置信区间', type: 'line', data: bandDelta, stack: 'conf', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(47,111,237,.10)' }, z: 1 },
      { name: '预测', type: 'line', data: predLine, smooth: true, symbol: 'circle', symbolSize: 5, lineStyle: { width: 2, color: UP, type: 'dashed' }, itemStyle: { color: UP }, z: 6,
        markLine: { silent: true, symbol: 'none', lineStyle: { color: '#bbb', type: 'dotted' }, data: [{ xAxis: allDates[nHist - 1] }] } },
    ]
  });
  chart.resize();
}

async function refreshAll() {
  try {
    await Promise.all([loadFunds(), loadNews()]);
    if (selectedCode) await loadDetail();
  } catch (e) { toast('刷新出错：' + e.message); }
}

$('btn-refresh').onclick = async () => {
  toast('正在刷新数据…');
  try { await api('/api/refresh'); } catch (e) {}
  await refreshAll();
  toast('已刷新');
};
$('pill-auto').onclick = () => {
  autoRefresh = !autoRefresh;
  $('pill-auto').textContent = '自动刷新：' + (autoRefresh ? '开' : '关');
  if (autoRefresh) startTimer(); else clearInterval(timer);
};

function startTimer() {
  clearInterval(timer);
  timer = setInterval(() => { if (autoRefresh) refreshAll(); }, 15000);
}

async function init() {
  await loadHealth();
  await refreshAll();
  startTimer();
  window.addEventListener('resize', () => chart && chart.resize());
}
init();
