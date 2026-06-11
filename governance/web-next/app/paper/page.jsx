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
          <div className="label">현재 포트폴리오 <span className="text-muted">(좌=숏 / 우=롱)</span></div>
          <div className="space-y-1.5 mt-1">
            {cfg.coins.map((c) => {
              const w = state?.weights?.[c] || 0;
              const carry = state?.funding_carry_by_coin?.[c];
              const max = Math.max(60, ...cfg.coins.map((x) => Math.abs(state?.weights?.[x] || 0)));
              const pctW = (Math.abs(w) / max) * 50;
              return (
                <div key={c} className="flex items-center gap-2">
                  <span className="text-xs font-bold w-10">{c}</span>
                  <div className="flex-1 h-4 rounded bg-bg border border-border relative overflow-hidden">
                    <div className="absolute top-0 bottom-0 left-1/2 w-px bg-border" />
                    <div className="absolute top-0 bottom-0"
                      style={{ background: w >= 0 ? '#26d07c' : '#f6465d',
                        width: pctW + '%', left: w >= 0 ? '50%' : 'auto',
                        right: w >= 0 ? 'auto' : '50%' }} />
                  </div>
                  <span className={`text-xs w-14 text-right stat-num ${cls(w)}`}>
                    {w > 0 ? '+' : ''}{w}%</span>
                  <span className="text-[10px] text-muted w-16 text-right stat-num"
                    title="펀딩 캐리(연)">
                    {carry != null ? (carry > 0 ? '+' : '') + carry + '%' : ''}</span>
                </div>
              );
            })}
          </div>
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
