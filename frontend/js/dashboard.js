import {request} from './api.js';
import {setState} from './state.js';

(function () {
  const el = id => document.getElementById(id);
  const safe = value => value == null || Number.isNaN(value) ? '--' : value;
  const money = value => value == null ? '--' : `¥${Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 2})}`;
  const percent = value => value == null ? '--' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}%`;
  const stateName = state => ({positive: '增强', neutral: '中性', negative: '减弱'}[state] || '暂无');

  window.loadQuantFlowDashboard = async function () {
    setState({loading: {dashboard: true}, errors: {}});
    try {
      const data = await request('/api/dashboard');
      setState({dashboard: data, portfolio: data.portfolio, watchlist: data.watchlist,
                loading: {dashboard: false}});
      const pf = data.portfolio || {}, perf = data.performance || {}, risk = data.risk || {};
      el('qf-asof').textContent = `更新于 ${data.generated_at || '--'}`;
      el('qf-asset').innerHTML = `<div class="asset-main"><span>我的资产</span><strong>${money(pf.total_value)}</strong><small>今日收益 <b class="${(perf.today_return || 0) >= 0 ? 'gain' : 'loss'}">${percent(perf.today_return)}</b></small></div>
        <div class="asset-metrics"><div><span>近 30 日</span><b>${percent(perf.return_30d)}</b></div><div><span>最大回撤</span><b>${percent(perf.max_drawdown == null ? null : perf.max_drawdown * 100)}</b></div><div><span>组合风险</span><b class="risk-${risk.risk_level || 'none'}">${({low:'低',medium:'中',high:'高'}[risk.risk_level] || '暂无')}</b></div></div>`;
      const changes = data.market_summary?.important_changes || [];
      el('qf-change-count').textContent = changes.length ? `${changes.length} 项` : '';
      el('qf-changes').innerHTML = changes.length ? changes.map(item => `<button class="task-row" data-qf-fund="${item.code}"><span class="signal-dot ${item.state}"></span><span><b>${item.name}</b><small>趋势${stateName(item.state)} · 评分 ${safe(item.trend_score)}</small></span><i>查看</i></button>`).join('') : '<div class="empty-state">当前没有需要优先处理的明显变化。</div>';
      const alerts = data.alerts || [];
      el('qf-risk').innerHTML = alerts.length ? alerts.map(item => `<div class="risk-row"><span>!</span><div><b>${item.message}</b><small>${item.code}</small></div></div>`).join('') : `<div class="empty-state">${risk.status === 'blocked_simulated_data' ? '实时数据暂时不可用，未生成组合风险。' : '当前没有触发风险提醒。'}</div>`;
      const watch = data.watchlist || [];
      el('qf-watchlist').innerHTML = watch.length ? `<table class="watch-table"><thead><tr><th>基金</th><th>今日</th><th>趋势</th><th>风险</th></tr></thead><tbody>${watch.map(item => `<tr data-qf-fund="${item.code}"><td><b>${item.name}</b><small>${item.code}</small></td><td class="${(item.day_change_pct || 0) >= 0 ? 'gain' : 'loss'}">${percent(item.day_change_pct)}</td><td>${stateName(item.signal?.state)}</td><td>${item.signal?.risk_score == null ? '--' : Math.round(item.signal.risk_score)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">在“发现”中添加关注基金。</div>';
      el('qf-summary').textContent = data.ai_summary?.text || '暂无摘要。';
    } catch (error) {
      setState({loading: {dashboard: false}, errors: {dashboard: error.message}});
      el('qf-asset').innerHTML = `<div class="empty-state">驾驶舱加载失败：${error.message}</div>`;
    }
  };

  document.addEventListener('click', event => {
    const target = event.target.closest('[data-qf-fund]');
    if (!target) return;
    document.dispatchEvent(new CustomEvent('qf-open-fund', {detail: {code: target.dataset.qfFund}}));
  });
})();
