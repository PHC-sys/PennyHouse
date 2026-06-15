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
  const [cash, setCash] = useState(0);
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
      body: JSON.stringify({ user: me, deposit: +deposit, votes: { ...votes, cash: +cash } }) });
    refresh();
  }
  async function reset() { await api(`/api/funds/${id}/reset`, { method: 'POST' }); refresh(); }
  async function redeem() {
    if (!confirm('내 지분을 회수(출금)하고 펀드에서 나갑니다. 계속할까요?')) return;
    try {
      const r = await api(`/api/funds/${id}/redeem`, {
        method: 'POST', body: JSON.stringify({ user: me }) });
      alert(`회수 완료: ${fmtUsd(r.redeemed)} (남은 참가자 ${r.remaining}명)`);
      refresh();
    } catch (e) { alert(e.message); }
  }
  async function removeFund() {
    if (!confirm('이 펀드를 영구 삭제합니다. 되돌릴 수 없어요. 계속할까요?')) return;
    try {
      await api(`/api/funds/${id}?user=${encodeURIComponent(me)}`, { method: 'DELETE' });
      router.push('/paper');
    } catch (e) { alert(e.message); }
  }

  if (!fund) return <div className="text-muted">로딩 중…</div>;
  const uni = fund.universe;
  const isParticipant = (state?.participants || []).some((p) => p.user === me);
  const isCreator = !!fund.creator && fund.creator === me;
  const canDelete = isCreator && state != null
    && (state.fund_equity <= 1e-6 || (state.participants || []).length === 0);
  const navData = (state?.nav_history || []).map((p) => ({ time: p.t, value: p.ret_pct }));

  return (
    <div className="space-y-4">
      <button className="btn-ghost py-1" onClick={() => router.push('/paper')}>← 펀드 목록</button>
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-lg font-bold">{fund.name}</h2>
        <span className="chip">{fund.kind === 'demo' ? 'Demo' : '실제'}</span>
        <span className="chip">{fund.visibility === 'private' ? '🔒 Private' : 'Public'}</span>
        <span className="chip">{state ? `${state.leverage}x` : ''}</span>
        {canDelete && (
          <button className="btn-ghost py-1 text-short ml-auto" onClick={removeFund}>
            펀드 삭제 (자금 0)
          </button>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* 투표 */}
        <div className="card space-y-3">
          <h3 className="font-semibold">🗳️ 투표하기 <span className="text-xs text-muted">나: {me}</span></h3>
          <div><div className="label">가상 예치금 ($)</div>
            <input className="input w-full" type="number" step="1000"
              value={deposit} onChange={(e) => setDeposit(e.target.value)} /></div>

          {/* 현금 보유 비율 */}
          <div className="rounded-xl border border-border p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold">💵 현금 보유 비율</span>
              <span className="text-xs text-muted">방향 모를 땐 현금 ↑</span>
            </div>
            <div className="flex gap-1.5 items-center">
              {[0, 10, 25, 50].map((v) => (
                <button key={v} onClick={() => setCash(v)}
                  className={`flex-1 py-1.5 text-xs rounded-lg border transition
                    ${+cash === v ? 'bg-brand text-bg border-brand' : 'border-border text-muted hover:text-fg'}`}>
                  {v}%</button>
              ))}
              <input type="number" min="0" max="100" value={cash}
                onChange={(e) => setCash(Math.max(0, Math.min(100, +e.target.value)))}
                className="input w-16 py-1.5 text-xs text-center" />
              <span className="text-xs text-muted">%</span>
            </div>
            <div className="text-[10px] text-muted mt-1.5">
              나머지 {100 - (+cash || 0)}%를 아래 종목 투표로 배분</div>
          </div>

          <div className="divide-y divide-border">
            {uni.map((c) => {
              const settled = state?.assets?.[c]?.settled;
              return (
              <div key={c} className="flex items-center gap-2 py-2">
                <span className="font-bold w-16 text-sm">{c.split(':').pop()}</span>
                {settled ? (
                  <div className="flex-1 text-xs text-muted py-1.5">
                    <span className="px-1.5 py-0.5 rounded bg-muted/20 text-[10px]">상장폐지 · 정산됨</span>
                    <span className="ml-1">최종가 현금 정산 — 투표 불가</span>
                  </div>
                ) : (
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
                )}
              </div>
              );
            })}
          </div>
          <button className="btn-primary w-full" onClick={submit}>투표 제출 / 갱신</button>
          {isParticipant && (
            <button className="btn-ghost w-full text-short" onClick={redeem}>내 지분 회수 (출금·탈퇴)</button>
          )}
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
            <div className="flex items-center justify-between">
              <div className="label mb-0">현재 포트폴리오</div>
              {(state?.cash_pct > 0 || state?.target_cash_pct > 0) && <span className="text-[10px] text-muted">
                현금 {state.cash_pct}%{state?.target_cash_pct ? ` (목표 ${state.target_cash_pct}%)` : ''}</span>}
            </div>
            <table className="w-full text-[11px] mt-1">
              <thead><tr className="text-muted">
                <th className="text-left py-1">자산</th><th className="text-right">비중</th>
                <th className="text-right">수익률</th><th className="text-right">펀딩(연)</th>
                <th className="text-right">평단</th><th className="text-right">청산가</th>
              </tr></thead>
              <tbody>
                {uni.map((c) => {
                  const a = state?.assets?.[c] || {};
                  const w = a.weight ?? 0;
                  const near = a.liq_dist_pct != null && a.liq_dist_pct < 10;
                  if (a.settled) return (
                    <tr key={c} className="border-t border-border/60 text-muted">
                      <td className="py-1.5 font-bold">{c.split(':').pop()}
                        <span className="ml-1 text-[8px] px-1 py-0.5 rounded bg-muted/20">정산됨</span></td>
                      <td className="text-right stat-num">0%</td>
                      <td className={`text-right stat-num ${cls(a.return_pct)}`}>{a.return_pct != null ? fmtPct(a.return_pct) : '—'}</td>
                      <td className="text-right">—</td>
                      <td className="text-right stat-num" title="상장폐지 최종가">{a.final_price != null ? smartNum(a.final_price) : '—'}</td>
                      <td className="text-right">—</td>
                    </tr>
                  );
                  return (
                    <tr key={c} className="border-t border-border/60">
                      <td className="py-1.5 font-bold">{c.split(':').pop()}
                        <span className={`ml-1 text-[9px] ${w >= 0 ? 'pos' : 'neg'}`}>{w >= 0 ? '롱' : '숏'}</span>
                        <span className="ml-1 text-[8px] text-muted">{a.quote}·{a.eff_leverage}x</span></td>
                      <td className={`text-right stat-num ${cls(w)}`}>{w > 0 ? '+' : ''}{w}%</td>
                      <td className={`text-right stat-num ${cls(a.return_pct)}`}>{a.return_pct != null ? fmtPct(a.return_pct) : '—'}</td>
                      <td className={`text-right stat-num ${cls(a.funding_carry)}`}>{a.funding_carry != null ? fmtPct(a.funding_carry) : '—'}</td>
                      <td className="text-right stat-num text-muted">{a.avg_entry != null ? smartNum(a.avg_entry) : '—'}</td>
                      <td className="text-right stat-num" title={a.liq_dist_pct != null ? `현재가 대비 ${a.liq_dist_pct}%` : ''}>
                        {a.liq_price != null
                          ? <span className={near ? 'neg' : 'text-muted'}>{smartNum(a.liq_price)}
                              <span className="text-[8px] ml-0.5">({a.liq_dist_pct}%)</span></span>
                          : <span className="text-muted">—</span>}</td>
                    </tr>
                  );
                })}
                {state?.cash_pct > 0 && (
                  <tr className="border-t border-border/60 text-muted">
                    <td className="py-1.5 font-bold">CASH <span className="text-[8px]">안전</span></td>
                    <td className="text-right stat-num">{state.cash_pct}%</td>
                    <td className="text-right">—</td><td className="text-right">—</td>
                    <td className="text-right">—</td><td className="text-right">—</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div><div className="label">실시간 NAV <span className="text-[9px]">분 단위 · UTC</span></div>
            <Line data={navData} height={180} area /></div>
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
