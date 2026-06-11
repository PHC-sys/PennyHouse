'use client';
import { useEffect, useState, useMemo } from 'react';
import { api, fmtPct, cls } from '@/components/api';
import { MultiLine, Candles, Line } from '@/components/Charts';

const SCEN_COLORS = {
  momentum: '#5b8def', contrarian: '#f6465d', ma_cross: '#a855f7',
  random: '#7d8a9c', always_long: '#f0b90b', perfect: '#26d07c', custom: '#22d3ee',
};
const INTERVALS = ['1h', '4h', '1d', '1w'];
const STANCE = [['강숏', -2], ['숏', -1], ['유지', 0], ['롱', 1], ['강롱', 2]];

export default function BacktestPage() {
  const [cfg, setCfg] = useState(null);
  const [scenMeta, setScenMeta] = useState({});
  const [profile, setProfile] = useState('aggressive');
  const [days, setDays] = useState(180);
  const [period, setPeriod] = useState(7);
  const [activeScen, setActiveScen] = useState(
    { momentum: true, contrarian: true, ma_cross: true, random: true, perfect: true, always_long: false });
  const [stance, setStance] = useState({});
  const [useStance, setUseStance] = useState(false);
  const [logScale, setLogScale] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // 차트 섹션
  const [coin, setCoin] = useState('BTC');
  const [interval, setInterval] = useState('1d');
  const [chartDays, setChartDays] = useState(180);
  const [candles, setCandles] = useState([]);
  const [funding, setFunding] = useState(null);
  const [relB, setRelB] = useState('ETH');
  const [relData, setRelData] = useState([]);

  useEffect(() => {
    api('/api/config').then((c) => {
      setCfg(c);
      const st = {}; c.coins.forEach((x) => (st[x] = 0)); setStance(st);
    }).catch((e) => setErr(e.message));
    api('/api/scenarios').then(setScenMeta).catch(() => {});
  }, []);

  async function run() {
    setLoading(true); setErr(null);
    try {
      const scenarios = Object.keys(activeScen).filter((s) => activeScen[s]);
      const body = { profile, days, rebalance_every: period, scenarios };
      if (useStance) body.custom_votes = stance;
      setResult(await api('/api/backtest', { method: 'POST', body: JSON.stringify(body) }));
    } catch (e) { setErr(e.message); } finally { setLoading(false); }
  }
  useEffect(() => { if (cfg) run(); /* eslint-disable-next-line */ }, [cfg]);

  // 차트 로드
  useEffect(() => {
    if (!cfg) return;
    api(`/api/prices/${coin}?days=${chartDays}&interval=${interval}`)
      .then((d) => setCandles(d.candles)).catch(() => setCandles([]));
    api(`/api/funding/${coin}?days=90`).then(setFunding).catch(() => setFunding(null));
  }, [cfg, coin, interval, chartDays]);
  useEffect(() => {
    if (!cfg) return;
    api(`/api/relative/${coin}/${relB}?days=${chartDays}&interval=${interval}`)
      .then((d) => setRelData(d.series)).catch(() => setRelData([]));
  }, [cfg, coin, relB, chartDays, interval]);

  const lines = useMemo(() => {
    if (!result) return [];
    const mk = (arr) => result.dates.map((t, i) => ({ time: t, value: arr[i] }));
    const out = [{ data: mk(result.benchmark.cum_return), color: '#ffffff', width: 1, dashed: true }];
    for (const s of Object.keys(result.scenarios))
      out.push({ data: mk(result.scenarios[s].cum_return), color: SCEN_COLORS[s] || '#888', width: 2 });
    return out;
  }, [result]);

  if (!cfg) return <div className="text-muted">로딩 중…</div>;

  return (
    <div className="space-y-5">
      {/* 컨트롤 */}
      <div className="card flex flex-wrap items-end gap-4">
        <Field label="펀드 프로파일">
          <select className="input" value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="aggressive">공격적 (T=7일, 5x)</option>
            <option value="conservative">보수적 (T=21일, 2x)</option>
          </select>
        </Field>
        <Field label="기간 (일)">
          <select className="input" value={days} onChange={(e) => setDays(+e.target.value)}>
            {[90, 180, 365, 730].map((d) => <option key={d} value={d}>{d}일</option>)}
          </select>
        </Field>
        <Field label="투표 주기 (일)">
          <select className="input" value={period} onChange={(e) => setPeriod(+e.target.value)}>
            <option value={1}>매일</option><option value={3}>3일</option><option value={7}>주간</option>
          </select>
        </Field>
        <button className="btn-primary" onClick={run} disabled={loading}>
          {loading ? '실행 중…' : '백테스트 실행 ▶'}
        </button>
        {result && <span className="text-warn text-xs self-center">
          적응형 alpha = {result.alpha} · {profile === 'aggressive' ? '5x' : '2x'}</span>}
      </div>

      {err && <div className="card border-short/40 text-short text-sm">⚠ {err}</div>}

      {/* 시나리오 토글 + 내 스탠스 */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="label mb-0 mr-1">표시 시나리오</span>
          {Object.keys(activeScen).map((s) => (
            <span key={s}
              className={`chip ${activeScen[s] ? 'chip-active' : ''}`}
              onClick={() => setActiveScen((p) => ({ ...p, [s]: !p[s] }))}>
              {scenMeta[s]?.label || s}
            </span>
          ))}
          <span className="ml-2 text-[11px] text-muted">스케일</span>
          <span className={`chip ${logScale ? 'chip-active' : ''}`}
            onClick={() => setLogScale((v) => !v)}>로그</span>
        </div>
        <div className="flex items-center gap-3 flex-wrap border-t border-border pt-3">
          <span className={`chip ${useStance ? 'chip-active' : ''}`}
            onClick={() => setUseStance((v) => !v)}>🎯 내 스탠스 포함</span>
          {useStance && cfg.coins.map((c) => (
            <div key={c} className="flex items-center gap-1">
              <span className="text-xs font-bold w-10">{c}</span>
              <select className="input py-1 text-xs"
                value={stance[c]} onChange={(e) => setStance((p) => ({ ...p, [c]: +e.target.value }))}>
                {STANCE.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* 수익률 + 지표 */}
      <div className="grid lg:grid-cols-5 gap-5">
        <div className="card lg:col-span-3">
          <h3 className="font-semibold mb-3">누적 수익률 <span className="text-muted text-xs">vs Buy&Hold</span></h3>
          <MultiLine lines={lines} height={320} logScale={logScale} />
          <div className="flex gap-3 flex-wrap mt-3 text-xs">
            <Lg color="#ffffff" name="Buy&Hold" />
            {result && Object.keys(result.scenarios).map((s) =>
              <Lg key={s} color={SCEN_COLORS[s]} name={result.labels?.[s] || s} />)}
          </div>
        </div>
        <div className="card lg:col-span-2 overflow-x-auto">
          <h3 className="font-semibold mb-3">성과 지표</h3>
          {result && <MetricsTable result={result} />}
          <p className="text-[11px] text-muted leading-relaxed mt-3">
            💡 <b>Perfect</b>가 압도하는 게 정상 — "투표가 정확하면 수익"이라는 메커니즘 검증입니다.
            실제 수익은 <b>참여자의 투표 품질</b>이 결정합니다.
          </p>
        </div>
      </div>

      {/* 종목 차트 */}
      <div className="card">
        <div className="flex items-center gap-3 flex-wrap mb-3">
          <h3 className="font-semibold">종목 차트 <span className="text-muted text-xs">Hyperliquid</span></h3>
          <div className="flex gap-1.5 ml-2">
            {cfg.coins.map((c) => (
              <span key={c} className={`chip ${coin === c ? 'chip-active' : ''}`}
                onClick={() => setCoin(c)}>{c}</span>)) }
          </div>
          <div className="flex gap-1.5 ml-auto">
            {INTERVALS.map((iv) => (
              <span key={iv} className={`chip ${interval === iv ? 'chip-active' : ''}`}
                onClick={() => setInterval(iv)}>{iv}</span>))}
          </div>
          <select className="input py-1 text-xs" value={chartDays}
            onChange={(e) => setChartDays(+e.target.value)}>
            {[30, 90, 180, 365, 730].map((d) => <option key={d} value={d}>{d}일</option>)}
          </select>
        </div>
        {funding?.current && (
          <div className="text-xs text-muted mb-2">
            현재 펀딩(연): <span className={cls(-(funding.current.annual_pct))}>
              {funding.current.annual_pct}%</span>
            <span className="ml-3">롱이면 지불 / 숏이면 수취</span>
          </div>
        )}
        <Candles data={candles} height={360} />
      </div>

      {/* 펀딩 + 상대가격 */}
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card">
          <h3 className="font-semibold mb-3">{coin} 펀딩비 추이 <span className="text-muted text-xs">연환산 %</span></h3>
          <Line data={funding?.series || []} height={220} color="#f0b90b" area />
        </div>
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <h3 className="font-semibold">상대가격</h3>
            <span className="text-muted text-sm">{coin} /</span>
            <select className="input py-1 text-xs" value={relB} onChange={(e) => setRelB(e.target.value)}>
              {cfg.coins.filter((c) => c !== coin).map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <Line data={relData} height={220} color="#a855f7" />
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return <div className="flex flex-col"><span className="label">{label}</span>{children}</div>;
}
function Lg({ color, name }) {
  return <span className="flex items-center gap-1.5">
    <i className="w-3.5 h-[3px] rounded-full inline-block" style={{ background: color }} />{name}</span>;
}
function MetricsTable({ result }) {
  const order = Object.keys(result.scenarios);
  return (
    <table className="w-full text-[13px]">
      <thead><tr className="text-muted">
        <th className="text-left font-medium py-1.5">시나리오</th>
        <th className="text-right font-medium">누적</th>
        <th className="text-right font-medium">연환산</th>
        <th className="text-right font-medium">Sharpe</th>
        <th className="text-right font-medium">낙폭</th>
        <th className="text-right font-medium">청산</th>
      </tr></thead>
      <tbody>
        {order.map((s) => {
          const m = result.metrics[s];
          return <tr key={s} className="border-t border-border">
            <td className="py-1.5">{result.labels?.[s] || s}</td>
            <td className={`text-right stat-num ${cls(m.cum_return)}`}>{fmtPct(m.cum_return)}</td>
            <td className={`text-right stat-num ${cls(m.ann_return)}`}>{fmtPct(m.ann_return)}</td>
            <td className="text-right stat-num">{m.sharpe}</td>
            <td className="text-right stat-num neg">{fmtPct(m.max_drawdown, false)}</td>
            <td className="text-right">{m.liquidated ? '⚠️' : '-'}</td>
          </tr>;
        })}
        <tr className="border-t border-border text-muted">
          <td className="py-1.5">Buy&Hold</td>
          <td className={`text-right stat-num ${cls(result.metrics.benchmark.cum_return)}`}>
            {fmtPct(result.metrics.benchmark.cum_return)}</td>
          <td className="text-right">-</td><td className="text-right">-</td>
          <td className="text-right stat-num neg">{fmtPct(result.metrics.benchmark.max_drawdown, false)}</td>
          <td className="text-right">-</td>
        </tr>
      </tbody>
    </table>
  );
}
