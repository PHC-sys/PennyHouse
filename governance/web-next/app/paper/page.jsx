'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, fmtPct, cls } from '@/components/api';
import { useMe } from '@/components/useMe';
import CreateFundModal from '@/components/CreateFundModal';

const TABS = [
  { key: 'all', label: '전체' },
  { key: 'mine', label: '내 펀드' },
  { key: 'demo', label: 'Demo' },
  { key: 'real', label: '실제' },
];

export default function FundListPage() {
  const router = useRouter();
  const [me] = useMe();
  const [funds, setFunds] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [tab, setTab] = useState('all');
  const [creating, setCreating] = useState(false);

  function load() {
    if (!me) return;
    api(`/api/funds?user=${encodeURIComponent(me)}`)
      .then((d) => setFunds(d.funds || []))
      .catch(() => setFunds([]))
      .finally(() => setLoaded(true));
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [me]);

  const shown = funds.filter((f) =>
    tab === 'all' ? true
      : tab === 'mine' ? f.creator === me  // 내가 '개설'한 펀드만 (투표만 한 건 제외)
        : f.kind === tab);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex gap-1.5">
          {TABS.map((t) => (
            <span key={t.key} className={`chip ${tab === t.key ? 'chip-active' : ''}`}
              onClick={() => setTab(t.key)}>{t.label}</span>
          ))}
        </div>
        <span className="text-xs text-muted">나: <b className="text-fg">{me}</b></span>
        <button className="btn-primary ml-auto" onClick={() => setCreating(true)}>➕ 펀드 개설</button>
      </div>

      <div className="grid gap-4"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
        {shown.map((f) => (
          <div key={f.id} onClick={() => router.push(`/paper/${f.id}`)}
            className="card cursor-pointer hover:border-brand/40 hover:shadow-glow transition">
            <div className="flex items-start justify-between mb-2">
              <div>
                <div className="font-bold flex items-center gap-2">
                  {f.name}
                  {f.is_mine && <span className="text-[9px] text-brand border border-brand/40 rounded px-1">내 펀드</span>}
                </div>
                <div className="flex gap-1.5 mt-1 text-[10px]">
                  <Badge>{f.kind === 'demo' ? 'Demo' : '실제'}</Badge>
                  <Badge>{f.visibility === 'private' ? '🔒 Private' : 'Public'}</Badge>
                  <Badge>{f.profile === 'aggressive' ? '5x' : f.profile === 'conservative' ? '2x' : '1x'}</Badge>
                </div>
              </div>
              <div className="text-right">
                {f.nav_ret_pct != null && (
                  <div className={`stat-num font-bold ${cls(f.nav_ret_pct)}`}>{fmtPct(f.nav_ret_pct)}</div>
                )}
                {f.funding_carry_annual_pct != null && (
                  <div className="text-[10px] text-muted">펀딩 <span className={cls(f.funding_carry_annual_pct)}>
                    {fmtPct(f.funding_carry_annual_pct)}</span></div>
                )}
              </div>
            </div>
            <div className="flex justify-between text-xs text-muted">
              <span>자산 {f.universe.length}종</span>
              <span>참여자 {f.participants}명</span>
            </div>
            <div className="flex gap-1 flex-wrap mt-2">
              {f.universe.slice(0, 6).map((s) => (
                <span key={s} className="text-[10px] text-muted bg-bg rounded px-1.5 py-0.5">
                  {s.split(':').pop()}</span>
              ))}
              {f.universe.length > 6 && <span className="text-[10px] text-muted">+{f.universe.length - 6}</span>}
            </div>
          </div>
        ))}
        {!loaded && <div className="text-muted animate-pulse">펀드 불러오는 중…</div>}
        {loaded && !shown.length && <div className="text-muted">펀드가 없습니다. 개설해보세요.</div>}
      </div>

      {creating && (
        <CreateFundModal me={me} onClose={() => setCreating(false)}
          onCreated={(f) => { setCreating(false); router.push(`/paper/${f.id}`); }} />
      )}
    </div>
  );
}

function Badge({ children }) {
  return <span className="text-muted border border-border rounded px-1.5 py-0.5">{children}</span>;
}
