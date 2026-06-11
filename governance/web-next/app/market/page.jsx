'use client';
import { useEffect, useState } from 'react';
import { api, cls } from '@/components/api';
import { Spark } from '@/components/Charts';
import AssetModal from '@/components/AssetModal';

const CATS = [
  { key: 'all', label: '전체' },
  { key: 'crypto', label: '크립토' },
  { key: 'tradfi', label: 'TradFi' },
  { key: 'preipo', label: 'Pre-IPO' },
];
const SUBS = {
  tradfi: [
    { key: '', label: '전체' },
    { key: 'stock', label: '주식' },
    { key: 'index', label: '지수' },
    { key: 'commodity', label: '원자재' },
    { key: 'fx', label: 'FX' },
  ],
};

export default function MarketPage() {
  const [cat, setCat] = useState('all');
  const [sub, setSub] = useState('');
  const [search, setSearch] = useState('');
  const [data, setData] = useState(null);
  const [sortKey, setSortKey] = useState('change_24h');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    const q = new URLSearchParams();
    if (cat !== 'all') q.set('category', cat);
    if (sub) q.set('sub', sub);
    if (search) q.set('search', search);
    q.set('limit', '120');
    api('/api/assets?' + q.toString()).then(setData).catch(() => setData(null));
  }, [cat, sub, search]);

  const assets = (data?.assets || []).slice().sort((a, b) => {
    const va = a[sortKey] ?? -999, vb = b[sortKey] ?? -999;
    return vb - va;
  });

  return (
    <div className="space-y-4">
      {/* 헤더/필터 */}
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex gap-1.5">
          {CATS.map((c) => (
            <span key={c.key} className={`chip ${cat === c.key ? 'chip-active' : ''}`}
              onClick={() => { setCat(c.key); setSub(''); }}>
              {c.label}{data?.counts && c.key !== 'all'
                ? ` ${data.counts[c.key] || 0}` : c.key === 'all' && data ? ` ${data.total}` : ''}
            </span>
          ))}
        </div>
        {cat === 'tradfi' && (
          <div className="flex gap-1.5 border-l border-border pl-3">
            {SUBS.tradfi.map((s) => (
              <span key={s.key} className={`chip ${sub === s.key ? 'chip-active' : ''}`}
                onClick={() => setSub(s.key)}>{s.label}</span>
            ))}
          </div>
        )}
        <input className="input ml-auto w-44" placeholder="검색 (예: NVDA)"
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="input py-1.5 text-xs" value={sortKey}
          onChange={(e) => setSortKey(e.target.value)}>
          <option value="change_24h">정렬: 24h 변동</option>
          <option value="funding_annual">정렬: 펀딩</option>
          <option value="price">정렬: 가격</option>
        </select>
      </div>

      {/* 타일 그리드 */}
      <div className="grid gap-3"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
        {assets.map((a) => <Tile key={a.symbol} a={a} onClick={() => setSelected(a)} />)}
        {!assets.length && <div className="text-muted">불러오는 중…</div>}
      </div>

      {selected && <AssetModal asset={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Tile({ a, onClick }) {
  const [spark, setSpark] = useState([]);
  useEffect(() => {
    let on = true;
    api(`/api/spark/${a.symbol}?days=30`).then((d) => on && setSpark(d.series)).catch(() => {});
    return () => { on = false; };
  }, [a.symbol]);
  const up = (a.change_24h ?? 0) >= 0;
  return (
    <div className="card p-3 hover:shadow-glow hover:border-brand/40 transition cursor-pointer"
      onClick={onClick}>
      <div className="flex items-start justify-between">
        <div>
          <div className="font-bold text-sm flex items-center gap-1.5">
            {a.display}
            <span className="text-[9px] text-muted uppercase border border-border rounded px-1">
              {a.sub || a.category}</span>
          </div>
          <div className="text-[11px] text-muted stat-num">
            {a.price >= 1 ? a.price.toLocaleString() : a.price}</div>
        </div>
        <div className="text-right">
          <div className={`stat-num text-sm font-semibold ${cls(a.change_24h)}`}>
            {a.change_24h != null ? (a.change_24h > 0 ? '+' : '') + a.change_24h + '%' : '—'}</div>
          <div className="text-[9px] text-muted">24h</div>
        </div>
      </div>
      <div className="my-1.5"><Spark data={spark} height={44} up={up} /></div>
      <div className="flex justify-between text-[10px] text-muted">
        <span title="현재 펀딩 연환산">펀딩 <span className={cls(-a.funding_annual)}>
          {a.funding_annual}%</span></span>
        <span>최근 30일 · 최대 {a.max_leverage}x</span>
      </div>
    </div>
  );
}
