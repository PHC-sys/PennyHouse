'use client';
import { useEffect, useState, useRef } from 'react';
import { api, fmtPct, fmtUsd, cls } from '@/components/api';
import { Line } from '@/components/Charts';

const STANCE = [['강숏', -2], ['숏', -1], ['유지', 0], ['롱', 1], ['강롱', 2]];

export default function PaperPage() {
  const [cfg, setCfg] = useState(null);
  const [user, setUser] = useState('나');
  const [deposit, setDeposit] = useState(10000);
  const [profile, setProfile] = useState('aggressive');
  const [votes, setVotes] = useState({});
  const [state, setState] = useState(null);
  const timer = useRef(null);

  useEffect(() => {
    api('/api/config').then((c) => {
      setCfg(c); const v = {}; c.coins.forEach((x) => (v[x] = 0)); setVotes(v);
    });
    refresh();
    timer.current = setInterval(refresh, 5000);
    return () => clearInterval(timer.current);
  }, []);

  function refresh() { api('/api/paper/state').then(setState).catch(() => {}); }
  async function submit() {
    await api('/api/paper/vote', { method: 'POST',
      body: JSON.stringify({ user, deposit, profile, votes }) });
    refresh();
  }
  async function reset() { await api('/api/paper/reset', { method: 'POST' }); refresh(); }

  if (!cfg) return <div className="text-muted">로딩 중…</div>;
  const navData = (state?.nav_history || []).map((p) => ({ time: p.t, value: p.ret_pct }));

  return (
    <div className="grid lg:grid-cols-2 gap-5">
      {/* 투표 */}
      <div className="card space-y-3">
        <h3 className="font-semibold">🗳️ 투표하기</h3>
        <div className="grid grid-cols-2 gap-3">
          <div><div className="label">닉네임</div>
            <input className="input w-full" value={user} onChange={(e) => setUser(e.target.value)} /></div>
          <div><div className="label">가상 예치금 ($)</div>
            <input className="input w-full" type="number" step="1000"
              value={deposit} onChange={(e) => setDeposit(+e.target.value)} /></div>
        </div>
        <div><div className="label">펀드 프로파일</div>
          <select className="input w-full" value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="aggressive">공격적 (5x)</option>
            <option value="conservative">보수적 (2x)</option>
            <option value="spot">현물 (1x, 레버리지 없음)</option>
          </select></div>

        <div className="divide-y divide-border">
          {cfg.coins.map((c) => (
            <div key={c} className="flex items-center gap-2 py-2">
              <span className="font-bold w-12">{c}</span>
              <div className="flex gap-1 flex-1">
                {STANCE.map(([l, v]) => {
                  const sel = votes[c] === v;
                  const tone = v > 0 ? 'bg-long text-bg border-long'
                    : v < 0 ? 'bg-short text-white border-short'
                    : 'bg-muted text-bg border-muted';
                  return <button key={v}
                    className={`flex-1 py-1.5 text-xs rounded-lg border transition
                      ${sel ? tone : 'border-border text-muted hover:text-fg'}`}
                    onClick={() => setVotes((p) => ({ ...p, [c]: v }))}>{l}</button>;
                })}
              </div>
            </div>
          ))}
        </div>
        <button className="btn-primary w-full" onClick={submit}>투표 제출 / 갱신</button>
        <button className="btn-ghost w-full" onClick={reset}>세션 초기화</button>
      </div>

      {/* 펀드 현황 */}
      <div className="card space-y-4">
        <h3 className="font-semibold">💰 펀드 현황</h3>
        <div className="grid grid-cols-2 gap-3">
          <Stat label="펀드 수익률" big
            value={state ? fmtPct(state.fund_return_pct) : '—'}
            tone={cls(state?.fund_return_pct)} />
          <Stat label="펀딩 캐리 (연)"
            value={state ? fmtPct(state.funding_carry_annual_pct) : '—'}
            tone={cls(state?.funding_carry_annual_pct)} />
        </div>
        <Stat label="펀드 자산" value={state ? fmtUsd(state.fund_equity) : '—'} />

        <div>
          <div className="flex items-center justify-between">
            <div className="label mb-0">현재 포트폴리오</div>
            <span className="text-[10px] text-muted">레버리지 {state?.leverage || '—'}x</span>
          </div>
          <table className="w-full text-[11px] mt-1.5">
            <thead><tr className="text-muted">
              <th className="text-left font-medium py-1">자산</th>
              <th className="text-right font-medium">비중</th>
              <th className="text-right font-medium">수익률</th>
              <th className="text-right font-medium" title="현재 펀딩이 1년 유지 가정">펀딩(연)</th>
              <th className="text-right font-medium">평단</th>
              <th className="text-right font-medium" title="추정 청산가까지 거리">청산까지</th>
            </tr></thead>
            <tbody>
              {cfg.coins.map((c) => {
                const a = state?.assets?.[c] || {};
                const w = a.weight ?? 0;
                return (
                  <tr key={c} className="border-t border-border/60">
                    <td className="py-1.5 font-bold">{c}
                      <span className={`ml-1 text-[9px] ${w >= 0 ? 'pos' : 'neg'}`}>
                        {w >= 0 ? '롱' : '숏'}</span></td>
                    <td className={`text-right stat-num ${cls(w)}`}>{w > 0 ? '+' : ''}{w}%</td>
                    <td className={`text-right stat-num ${cls(a.return_pct)}`}>
                      {a.return_pct != null ? fmtPct(a.return_pct) : '—'}</td>
                    <td className={`text-right stat-num ${cls(a.funding_carry)}`}>
                      {a.funding_carry != null ? fmtPct(a.funding_carry) : '—'}</td>
                    <td className="text-right stat-num text-muted">
                      {a.avg_entry != null ? a.avg_entry.toLocaleString() : '—'}</td>
                    <td className="text-right stat-num">
                      {a.liq_dist_pct != null
                        ? <span className={a.liq_dist_pct < 10 ? 'neg' : 'text-muted'}>
                            {a.liq_dist_pct}%</span>
                        : <span className="text-muted">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-[10px] text-muted mt-1">
            펀딩(연)=현재 펀딩레이트 1년 유지 가정 · 롱=지불(−)/숏=수취(+) · 청산가는 추정치</p>
        </div>

        <div><div className="label">실시간 NAV</div><Line data={navData} height={180} area /></div>
      </div>

      {/* 리더보드 */}
      <div className="card lg:col-span-2">
        <h3 className="font-semibold mb-3">🏆 리더보드</h3>
        <table className="w-full text-[13px]">
          <thead><tr className="text-muted">
            <th className="text-left font-medium py-1.5">#</th>
            <th className="text-left font-medium">닉네임</th>
            <th className="text-right font-medium">예치금</th>
            <th className="text-right font-medium">지분</th>
            <th className="text-right font-medium">평가액</th>
            <th className="text-right font-medium">수익률</th>
          </tr></thead>
          <tbody>
            {(state?.participants || []).map((p, i) => (
              <tr key={p.user} className="border-t border-border">
                <td className="py-1.5">{i + 1}</td><td>{p.user}</td>
                <td className="text-right stat-num">{fmtUsd(p.deposit)}</td>
                <td className="text-right stat-num">{p.share_pct}%</td>
                <td className="text-right stat-num">{fmtUsd(p.paper_value)}</td>
                <td className={`text-right stat-num ${cls(p.ret_pct)}`}>{fmtPct(p.ret_pct)}</td>
              </tr>
            ))}
            {!state?.participants?.length && (
              <tr><td colSpan={6} className="text-center text-muted py-3">
                아직 투표한 참여자가 없습니다</td></tr>)}
          </tbody>
        </table>
        <p className="text-[11px] text-muted mt-3">
          돈 없이 메커니즘을 체험하는 모드입니다. HL 실시간 가격으로 가상 포지션을 평가합니다.</p>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = '', big = false }) {
  return (
    <div className="flex flex-col">
      <span className="label">{label}</span>
      <span className={`stat-num ${big ? 'text-3xl font-extrabold' : 'text-lg font-semibold'} ${tone}`}>
        {value}</span>
    </div>
  );
}
