'use client';
import { useEffect, useRef, useState } from 'react';
import { api, cls, smartNum } from '@/components/api';
import { Spark } from '@/components/Charts';
import AssetModal from '@/components/AssetModal';
import AssetPicker, { useFavs, VOL } from '@/components/AssetPicker';
import { useLiveMids } from '@/components/useLive';

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
  const [sortKey, setSortKey] = useState('volume_24h');
  const [selected, setSelected] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [favs, toggleFav] = useFavs();

  useEffect(() => {
    const q = new URLSearchParams();
    if (cat !== 'all') q.set('category', cat);
    if (sub) q.set('sub', sub);
    if (search) q.set('search', search);
    q.set('limit', '120');
    api('/api/assets?' + q.toString()).then(setData).catch(() => setData(null));
  }, [cat, sub, search]);

  // ⌘K / Ctrl+K 로 팔레트 열기
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault(); setPickerOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const assets = (data?.assets || []).slice().sort((a, b) => {
    const fa = favs[a.symbol] ? 1 : 0, fb = favs[b.symbol] ? 1 : 0;
    if (fa !== fb) return fb - fa;
    const va = a[sortKey] ?? -1e18, vb = b[sortKey] ?? -1e18;
    return vb - va;
  });

  // 라이브 가격 (현재 목록 자산만 구독)
  const { prices: live, flash } = useLiveMids(assets.map((a) => a.symbol));

  // 스파크라인: 화면에 보이는 타일만 배치로 lazy 로드 (점진적 렌더)
  const [sparks, setSparks] = useState({});
  const requestedRef = useRef(new Set());
  const pendingRef = useRef(new Set());
  const flushTimer = useRef(null);

  function requestSpark(symbol) {
    if (requestedRef.current.has(symbol)) return;
    requestedRef.current.add(symbol);
    pendingRef.current.add(symbol);
    clearTimeout(flushTimer.current);
    flushTimer.current = setTimeout(() => {
      const syms = [...pendingRef.current];
      pendingRef.current.clear();
      if (!syms.length) return;
      api('/api/sparks', { method: 'POST', body: JSON.stringify({ symbols: syms, days: 14 }) })
        .then((d) => setSparks((p) => ({ ...p, ...d.sparks }))).catch(() => {});
    }, 120);  // 잠깐 모아서 한 번에 (스크롤 중 들어온 것들 묶음)
  }

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
        <button className="btn-ghost ml-auto flex items-center gap-2" onClick={() => setPickerOpen(true)}>
          🔍 빠른 검색 <kbd className="text-[10px] border border-border rounded px-1">⌘K</kbd>
        </button>
        <select className="input py-1.5 text-xs" value={sortKey}
          onChange={(e) => setSortKey(e.target.value)}>
          <option value="volume_24h">정렬: 거래량</option>
          <option value="change_24h">정렬: 24h 변동</option>
          <option value="funding_annual">정렬: 펀딩</option>
          <option value="price">정렬: 가격</option>
        </select>
      </div>

      {/* 타일 그리드 */}
      <div className="grid gap-3"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
        {assets.map((a) => <Tile key={a.symbol} a={a} spark={sparks[a.symbol]}
          live={live[a.symbol]} flash={flash[a.symbol]}
          onVisible={() => requestSpark(a.symbol)}
          onClick={() => setSelected(a)}
          fav={!!favs[a.symbol]} onFav={() => toggleFav(a.symbol)} />)}
        {!assets.length && <div className="text-muted">불러오는 중…</div>}
      </div>

      {selected && <AssetModal asset={selected} onClose={() => setSelected(null)} />}
      <AssetPicker open={pickerOpen} onClose={() => setPickerOpen(false)}
        onSelect={(a) => setSelected(a)} title="종목 검색" />
    </div>
  );
}

function Tile({ a, spark, live, flash, onVisible, onClick, fav, onFav }) {
  // 라이브 가격이 있으면 그것으로, 등락도 prevDay 기준 재계산
  const price = live ?? a.price;
  const prevDay = a.change_24h != null ? a.price / (1 + a.change_24h / 100) : null;
  const change = (prevDay && live) ? (live / prevDay - 1) * 100 : a.change_24h;
  const up = (change ?? 0) >= 0;
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) { onVisible(); io.disconnect(); }
    }, { rootMargin: '200px' });  // 화면 근처 오면 미리 로드
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={ref} className="card p-3 hover:shadow-glow hover:border-brand/40 transition cursor-pointer"
      onClick={onClick}>
      <div className="flex items-start justify-between">
        <div>
          <div className="font-bold text-sm flex items-center gap-1.5">
            <button className={fav ? 'text-warn' : 'text-border hover:text-muted'}
              onClick={(e) => { e.stopPropagation(); onFav(); }}>★</button>
            {a.display}
            <span className="text-[9px] text-muted uppercase border border-border rounded px-1">
              {a.sub || a.category}</span>
          </div>
          <div className={`text-[11px] text-muted stat-num inline-block px-1 -mx-1
            ${flash === 'up' ? 'flash-up' : flash === 'down' ? 'flash-down' : ''}`}>
            {smartNum(price)}</div>
        </div>
        <div className="text-right">
          <div className={`stat-num text-sm font-semibold ${cls(change)}`}>
            {change != null ? (change > 0 ? '+' : '') + change.toFixed(2) + '%' : '—'}</div>
          <div className="text-[9px] text-muted">24h</div>
        </div>
      </div>
      <div className="my-1.5 h-11">
        {spark
          ? <div className="animate-fadein h-11"><Spark data={spark} height={44} up={up} /></div>
          : <div className="h-11 rounded bg-bg/40" />}
      </div>
      <div className="flex justify-between text-[10px] text-muted">
        <span title="현재 펀딩 연환산">펀딩 <span className={cls(-a.funding_annual)}>
          {a.funding_annual}%</span></span>
        <span title="24h 거래량">Vol {VOL(a.volume_24h)} · {a.max_leverage}x</span>
      </div>
    </div>
  );
}
