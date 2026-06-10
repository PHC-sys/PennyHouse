// ──────────────────────────────────────────────────────────────
// GovernanceFund 백테스트 & 페이퍼 트레이딩 프론트
// ──────────────────────────────────────────────────────────────
const API = '';  // 동일 오리진
let CONFIG = null;
const SCEN_COLORS = {momentum:'#58a6ff', contrarian:'#f85149',
  random:'#8b949e', perfect:'#d29922'};
const SCEN_LABELS = {momentum:'모멘텀', contrarian:'역추세',
  random:'랜덤', perfect:'완벽예측(상한)'};

// 탭 전환
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('tab-' + t.dataset.tab).classList.add('active');
  if (t.dataset.tab === 'paper') refreshPaper();
});

async function init() {
  CONFIG = await (await fetch(API + '/api/config')).json();
  buildCoinButtons();
  buildVoteRows();
  loadPriceChart(CONFIG.coins[0]);
  runBacktest();
  startPaperPolling();
}

// ════════════ 백테스트 ════════════
let btChart, btSeries = {};
function ensureBtChart() {
  if (btChart) return;
  btChart = LightweightCharts.createChart(document.getElementById('bt-chart'), {
    layout:{background:{color:'#161b22'}, textColor:'#8b949e'},
    grid:{vertLines:{color:'#21262d'}, horzLines:{color:'#21262d'}},
    timeScale:{timeVisible:false}, height:280,
  });
  new ResizeObserver(() => btChart.applyOptions({width:document.getElementById('bt-chart').clientWidth}))
    .observe(document.getElementById('bt-chart'));
}

async function runBacktest() {
  const btn = document.getElementById('bt-run');
  btn.textContent = '실행 중...'; btn.disabled = true;
  try {
    const body = {
      profile: document.getElementById('bt-profile').value,
      days: +document.getElementById('bt-days').value,
      rebalance_every: +document.getElementById('bt-period').value,
      scenarios: ['momentum','contrarian','random','perfect'],
    };
    const r = await (await fetch(API+'/api/backtest', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})).json();
    if (r.detail) { alert(r.detail); return; }
    document.getElementById('bt-alpha').textContent =
      `적응형 alpha = ${r.alpha} (투표주기 ${body.rebalance_every}일 기준)`;
    drawBacktest(r);
  } finally { btn.textContent = '백테스트 실행 ▶'; btn.disabled = false; }
}

function drawBacktest(r) {
  ensureBtChart();
  Object.values(btSeries).forEach(s => btChart.removeSeries(s));
  btSeries = {};
  const mkData = arr => r.dates.map((t,i) => ({time:t, value:arr[i]}));

  // benchmark
  btSeries.bh = btChart.addLineSeries({color:'#ffffff', lineWidth:1,
    lineStyle:LightweightCharts.LineStyle.Dashed});
  btSeries.bh.setData(mkData(r.benchmark.cum_return));

  for (const s of Object.keys(r.scenarios)) {
    btSeries[s] = btChart.addLineSeries({color:SCEN_COLORS[s], lineWidth:2});
    btSeries[s].setData(mkData(r.scenarios[s].cum_return));
  }
  btChart.timeScale().fitContent();

  // legend
  const leg = document.getElementById('bt-legend');
  leg.innerHTML = `<span><i style="background:#fff"></i>Buy&Hold</span>` +
    Object.keys(r.scenarios).map(s =>
      `<span><i style="background:${SCEN_COLORS[s]}"></i>${SCEN_LABELS[s]}</span>`).join('');

  // metrics table
  const m = r.metrics;
  const rows = Object.keys(r.scenarios).map(s => {
    const x = m[s];
    return `<tr><td>${SCEN_LABELS[s]}</td>
      <td class="${cls(x.cum_return)}">${x.cum_return}%</td>
      <td class="${cls(x.ann_return)}">${x.ann_return}%</td>
      <td>${x.sharpe}</td>
      <td class="neg">${x.max_drawdown}%</td>
      <td>${x.win_rate}%</td>
      <td>${x.liquidated?'⚠️':'-'}</td></tr>`;
  }).join('');
  const bh = m.benchmark;
  document.getElementById('bt-metrics').innerHTML = `<table>
    <thead><tr><th>시나리오</th><th>누적</th><th>연환산</th><th>Sharpe</th>
      <th>최대낙폭</th><th>승률</th><th>청산</th></tr></thead>
    <tbody>${rows}
    <tr><td>Buy&Hold</td><td class="${cls(bh.cum_return)}">${bh.cum_return}%</td>
      <td>-</td><td>-</td><td class="neg">${bh.max_drawdown}%</td><td>-</td><td>-</td></tr>
    </tbody></table>`;
}
const cls = v => v > 0 ? 'pos' : (v < 0 ? 'neg' : '');

// ════════════ 종목 차트 ════════════
let priceChart, candleSeries, activeCoin;
function buildCoinButtons() {
  const box = document.getElementById('coin-buttons');
  box.innerHTML = CONFIG.coins.map(c =>
    `<button class="coin-btn" data-coin="${c}">${c}</button>`).join('');
  box.querySelectorAll('.coin-btn').forEach(b => b.onclick = () => loadPriceChart(b.dataset.coin));
}
async function loadPriceChart(coin) {
  activeCoin = coin;
  document.querySelectorAll('.coin-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.coin === coin));
  if (!priceChart) {
    priceChart = LightweightCharts.createChart(document.getElementById('price-chart'), {
      layout:{background:{color:'#161b22'}, textColor:'#8b949e'},
      grid:{vertLines:{color:'#21262d'}, horzLines:{color:'#21262d'}}, height:360,
    });
    candleSeries = priceChart.addCandlestickSeries({
      upColor:'#3fb950', downColor:'#f85149', borderVisible:false,
      wickUpColor:'#3fb950', wickDownColor:'#f85149'});
    new ResizeObserver(() => priceChart.applyOptions({width:document.getElementById('price-chart').clientWidth}))
      .observe(document.getElementById('price-chart'));
  }
  const r = await (await fetch(`${API}/api/prices/${coin}?days=90`)).json();
  if (r.candles) { candleSeries.setData(r.candles); priceChart.timeScale().fitContent(); }
}

// ════════════ 페이퍼 트레이딩 ════════════
const voteState = {};
function buildVoteRows() {
  const box = document.getElementById('vote-rows');
  const opts = [[-2,'강숏'],[-1,'숏'],[0,'유지'],[1,'롱'],[2,'강롱']];
  box.innerHTML = CONFIG.coins.map(c => {
    voteState[c] = 0;
    return `<div class="vote-row"><span class="coin">${c}</span>
      <div class="vote-opts">${opts.map(([v,l]) =>
        `<div class="vote-opt" data-coin="${c}" data-v="${v}">${l}</div>`).join('')}</div></div>`;
  }).join('');
  box.querySelectorAll('.vote-opt').forEach(o => o.onclick = () => {
    const c = o.dataset.coin, v = +o.dataset.v;
    voteState[c] = v;
    box.querySelectorAll(`.vote-opt[data-coin="${c}"]`).forEach(x => {
      x.className = 'vote-opt';
      if (+x.dataset.v === v) x.classList.add(v>0?'sel-long':(v<0?'sel-short':'sel-hold'));
    });
  });
  // 기본 유지 표시
  box.querySelectorAll('.vote-opt[data-v="0"]').forEach(x => x.classList.add('sel-hold'));
}

document.getElementById('pp-submit').onclick = async () => {
  const body = {
    user: document.getElementById('pp-user').value || '익명',
    deposit: +document.getElementById('pp-deposit').value,
    profile: document.getElementById('pp-profile').value,
    votes: {...voteState},
  };
  await fetch(API+'/api/paper/vote', {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  refreshPaper();
};
document.getElementById('pp-reset').onclick = async () => {
  await fetch(API+'/api/paper/reset', {method:'POST'});
  refreshPaper();
};

let navChart, navSeries;
async function refreshPaper() {
  const s = await (await fetch(API+'/api/paper/state')).json();
  const ret = s.fund_return_pct;
  const el = document.getElementById('pp-return');
  el.textContent = (ret>=0?'+':'') + ret + '%';
  el.className = 'value ' + cls(ret);
  document.getElementById('pp-equity').textContent = '$' + s.fund_equity.toLocaleString();

  // weights
  const maxW = Math.max(60, ...CONFIG.coins.map(c => Math.abs(s.weights[c])));
  document.getElementById('pp-weights').innerHTML = CONFIG.coins.map(c => {
    const w = s.weights[c], tgt = s.target ? s.target[c] : 0;
    const half = 50 / maxW * Math.abs(w);
    const color = w>=0 ? 'var(--green)' : 'var(--red)';
    const side = w>=0 ? 'left:50%' : `right:50%`;
    return `<div class="wrow"><span class="c">${c}</span>
      <div class="wbar"><div class="mid"></div>
        <div class="fill" style="${side};width:${half}%;background:${color}"></div></div>
      <span class="pct ${cls(w)}">${w>0?'+':''}${w}%</span></div>`;
  }).join('');

  // nav chart
  if (!navChart) {
    navChart = LightweightCharts.createChart(document.getElementById('pp-nav-chart'), {
      layout:{background:{color:'#161b22'}, textColor:'#8b949e'},
      grid:{vertLines:{color:'#21262d'}, horzLines:{color:'#21262d'}}, height:200,
      timeScale:{timeVisible:true},
    });
    navSeries = navChart.addLineSeries({color:'#58a6ff', lineWidth:2});
    new ResizeObserver(() => navChart.applyOptions({width:document.getElementById('pp-nav-chart').clientWidth}))
      .observe(document.getElementById('pp-nav-chart'));
  }
  if (s.nav_history.length) {
    // 동일 타임스탬프 중복 제거 (lightweight-charts 요구)
    const seen = new Set();
    const data = [];
    for (const p of s.nav_history) {
      if (seen.has(p.t)) continue; seen.add(p.t);
      data.push({time:p.t, value:p.ret_pct});
    }
    navSeries.setData(data);
  }

  // leaderboard
  const tb = document.querySelector('#pp-leaderboard tbody');
  tb.innerHTML = s.participants.map((p,i) =>
    `<tr><td>${i+1}</td><td>${p.user}</td><td>$${p.deposit.toLocaleString()}</td>
      <td>${p.share_pct}%</td><td>$${p.paper_value.toLocaleString()}</td>
      <td class="${cls(p.ret_pct)}">${p.ret_pct>0?'+':''}${p.ret_pct}%</td></tr>`).join('')
    || '<tr><td colspan="6" style="text-align:center;color:var(--muted)">아직 투표한 참여자가 없습니다</td></tr>';
}

function startPaperPolling() {
  setInterval(() => {
    if (document.getElementById('tab-paper').classList.contains('active')) refreshPaper();
  }, 5000);
}

document.getElementById('bt-run').onclick = runBacktest;
init();
