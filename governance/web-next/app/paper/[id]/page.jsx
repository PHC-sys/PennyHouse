'use client';
import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api, fmtPct, fmtUsd, cls, smartNum } from '@/components/api';
import { useMe } from '@/components/useMe';
import { Line } from '@/components/Charts';

const STANCE = [['강숏', -2], ['숏', -1], ['유지', 0], ['롱', 1], ['강롱', 2]];

export default function FundDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [me] = useMe();
  const [fund, setFund] = useState(null);
  const [state, setState] = useState(null);
  const [deposit, setDeposit] = useState(10000);
  const [votes, setVotes] = useState({});
  const timer = useRef(null);

  useEffect(() => {
    api(`/api/funds/${id}`).then((f) => {
      setFund(f);
      const v = {}; f.universe.forEach((s) => (v[s] = 0)); setVotes(v);
    }).catch(() => setFund(null));
    refresh();
    timer.current = setInterval(refresh, 5000);
    return () => clearInterval(timer.current);
    // eslint-disable-next-line
  }, [id]);

  function refresh() { api(`/api/funds/${id}/state`).then(setState).catch(() => {}); }
  async function submit() {
    await api(`/api/funds/${id}/vote`, { method: 'POST',
      body: JSON.stringify({ user: me, deposit: +deposit, votes }) });
    refresh();
  }
  async function reset() { await api(`/api/funds/${id}/reset`, { method: 'POST' }); refresh(); }

  if (!fund) return <div className="text-muted">로딩 중…</div>;
  const uni = fund.universe;
  const navData = (state?.nav_history || []).map((p) => ({ time: p.t, value: p.ret_pct }));

  return (
    <div className="space-y-4">
      <button className="btn-ghost py-1" onClick={() => router.push('/paper')}>← 펀드 목록</button>
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-lg font-bold">{fund.name}</h2>
        <span className="chip">{fund.kind === 'demo' ? 'Demo' : '실제'}</span>
        <span className="chip">{fund.visibility === 'private' ? '🔒 Private' : 'Public'}</span>
        <span className="chip">{state ? `${state.leverage}x` : ''}</span>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* 투표 */}
        <div className="card space-y-3">
          <h3 className="font-semibold">🗳️ 투표하기 <span className="text-xs text-muted">나: {me}</span></h3>
          <div><div className="label">가상 예치금 ($)</div>
            <input className="input w-full" type="number" step="1000"
              value={deposit} onChange={(e) => setDeposit(e.target.value)} /></div>
          <div className="divide-y divide-border">
            {uni.map((c) => (
              <div key={c} className="flex items-center gap-2 py-2">
                <span className="font-bold w-16 text-sm">{c.split(':').pop()}</span>
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

        {/* 현황 */}
        <div className="card space-y-4">
          <h3 className="font-semibold">💰 펀드 현황</h3>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="펀드 수익률" big value={state ? fmtPct(state.fund_return_pct) : '—'}
              tone={cls(state?.fund_return_pct)} />
            <Stat label="펀딩 캐리 (연)" value={state ? fmtPct(state.funding_carry_annual_pct) : '—'}
              tone={cls(state?.funding_carry_annual_pct)} />
          </div>
          <Stat label="펀드 자산" value={state ? fmtUsd(state.fund_equity) : '—'} />

          <div>
            <div className="label">현재 포트폴리오</div>
            <table className="w-full text-[11px] mt-1">
              <thead><tr className="text-muted">
                <th className="text-left py-1">자산</th><th className="text-right">비중</th>
                <th className="text-right">수익률</th><th className="text-right">펀딩(연)</th>
                <th className="text-right">평단</th><th className="text-right">청산까지</th>
              </tr></thead>
              <tbody>
                {uni.map((c) => {
                  const a = state?.assets?.[c] || {};
                  const w = a.weight ?? 0;
                  return (
                    <tr key={c} className="border-t border-border/60">
                      <td className="py-1.5 font-bold">{c.split(':').pop()}
                        <span className={`ml-1 text-[9px] ${w >= 0 ? 'pos' : 'neg'}`}>{w >= 0 ? '롱' : '숏'}</span></td>
                      <td className={`text-right stat-num ${cls(w)}`}>{w > 0 ? '+' : ''}{w}%</td>
                      <td className={`text-right stat-num ${cls(a.return_pct)}`}>{a.return_pct != null ? fmtPct(a.return_pct) : '—'}</td>
                      <td className={`text-right stat-num ${cls(a.funding_carry)}`}>{a.funding_carry != null ? fmtPct(a.funding_carry) : '—'}</td>
                      <td className="text-right stat-num text-muted">{a.avg_entry != null ? smartNum(a.avg_entry) : '—'}</td>
                      <td className="text-right stat-num">{a.liq_dist_pct != null
                        ? <span className={a.liq_dist_pct < 10 ? 'neg' : 'text-muted'}>{a.liq_dist_pct}%</span>
                        : <span className="text-muted">—</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div><div className="label">실시간 NAV</div><Line data={navData} height={180} area /></div>
        </div>
      </div>

      {/* 리더보드 */}
      <div className="card">
        <h3 className="font-semibold mb-3">🏆 리더보드</h3>
        <table className="w-full text-[13px]">
          <thead><tr className="text-muted">
            <th className="text-left py-1.5">#</th><th className="text-left">닉네임</th>
            <th className="text-right">예치금</th><th className="text-right">지분</th>
            <th className="text-right">평가액</th><th className="text-right">수익률</th>
          </tr></thead>
          <tbody>
            {(state?.participants || []).map((p, i) => (
              <tr key={p.user} className={`border-t border-border ${p.user === me ? 'text-brand' : ''}`}>
                <td className="py-1.5">{i + 1}</td><td>{p.user}{p.user === me ? ' (나)' : ''}</td>
                <td className="text-right stat-num">{fmtUsd(p.deposit)}</td>
                <td className="text-right stat-num">{p.share_pct}%</td>
                <td className="text-right stat-num">{fmtUsd(p.paper_value)}</td>
                <td className={`text-right stat-num ${cls(p.ret_pct)}`}>{fmtPct(p.ret_pct)}</td>
              </tr>
            ))}
            {!state?.participants?.length && (
              <tr><td colSpan={6} className="text-center text-muted py-3">아직 참여자가 없습니다</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = '', big = false }) {
  return (
    <div className="flex flex-col">
      <span className="label">{label}</span>
      <span className={`stat-num ${big ? 'text-3xl font-extrabold' : 'text-lg font-semibold'} ${tone}`}>{value}</span>
    </div>
  );
}
