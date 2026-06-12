'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api, cls, smartNum } from '@/components/api';

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'tradfi', label: 'TradFi' },
  { key: 'preipo', label: 'Pre-IPO' },
];
const FMT = smartNum;
const VOL = (v) => !v ? '—' : v >= 1e9 ? (v / 1e9).toFixed(1) + 'B'
  : v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : (v / 1e3).toFixed(0) + 'K';

// 즐겨찾기 (localStorage)
function useFavs() {
  const [favs, setFavs] = useState({});
  useEffect(() => {
    try { setFavs(JSON.parse(localStorage.getItem('gf_favs') || '{}')); } catch {}
  }, []);
  const toggle = (sym) => setFavs((p) => {
    const n = { ...p }; if (n[sym]) delete n[sym]; else n[sym] = 1;
    localStorage.setItem('gf_favs', JSON.stringify(n)); return n;
  });
  return [favs, toggle];
}

/**
 * 커맨드 팔레트형 자산 선택기.
 * props: open, onClose, onSelect(asset), title
 */
export default function AssetPicker({ open, onClose, onSelect, title = '자산 검색' }) {
  const [assets, setAssets] = useState([]);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState('all');
  const [cursor, setCursor] = useState(0);
  const [favs, toggleFav] = useFavs();
  const inputRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => {
    if (open) {
      api('/api/assets?limit=500').then((d) => setAssets(d.assets || [])).catch(() => {});
      setQ(''); setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const filtered = useMemo(() => {
    let list = assets;
    if (tab !== 'all') list = list.filter((a) => a.category === tab);
    if (q) {
      const u = q.toUpperCase();
      list = list.filter((a) => a.display.toUpperCase().includes(u));
    }
    // 즐겨찾기 우선 → 거래량 순
    return [...list].sort((a, b) => {
      const fa = favs[a.symbol] ? 1 : 0, fb = favs[b.symbol] ? 1 : 0;
      if (fa !== fb) return fb - fa;
      return (b.volume_24h || 0) - (a.volume_24h || 0);
    }).slice(0, 200);
  }, [assets, tab, q, favs]);

  useEffect(() => { if (cursor >= filtered.length) setCursor(0); }, [filtered, cursor]);

  function onKey(e) {
    if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); return onClose(); }
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, filtered.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    if (e.key === 'Enter') { e.preventDefault(); const a = filtered[cursor]; if (a) { onSelect(a); onClose(); } }
  }
  useEffect(() => {
    const el = listRef.current?.children[cursor];
    el?.scrollIntoView({ block: 'nearest' });
  }, [cursor]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-start justify-center pt-[8vh] px-4"
      onClick={onClose}>
      <div className="bg-surface border border-border rounded-2xl shadow-glow w-full max-w-[680px]
        overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* 검색창 */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <span className="text-muted">🔍</span>
          <input ref={inputRef} className="flex-1 bg-transparent outline-none text-sm"
            placeholder={`${title} (예: NVDA, OPENAI)`} value={q}
            onChange={(e) => { setQ(e.target.value); setCursor(0); }} onKeyDown={onKey} />
          <kbd className="text-[10px] text-muted border border-border rounded px-1.5 py-0.5">ESC</kbd>
        </div>
        {/* 탭 */}
        <div className="flex gap-1.5 px-4 py-2 border-b border-border">
          {TABS.map((t) => (
            <span key={t.key} className={`chip ${tab === t.key ? 'chip-active' : ''}`}
              onClick={() => { setTab(t.key); setCursor(0); }}>{t.label}</span>
          ))}
        </div>
        {/* 리스트 */}
        <div ref={listRef} className="max-h-[52vh] overflow-y-auto">
          {filtered.map((a, i) => (
            <div key={a.symbol}
              className={`flex items-center gap-3 px-4 py-2 cursor-pointer text-sm
                ${i === cursor ? 'bg-card' : 'hover:bg-card/60'}`}
              onMouseEnter={() => setCursor(i)}
              onClick={() => { onSelect(a); onClose(); }}>
              <button className={favs[a.symbol] ? 'text-warn' : 'text-border hover:text-muted'}
                onClick={(e) => { e.stopPropagation(); toggleFav(a.symbol); }}>★</button>
              <span className="font-bold w-24">{a.display}
                <span className="ml-1 text-[9px] uppercase text-muted">{a.sub || a.category}</span></span>
              <span className="stat-num w-24 text-right text-muted">{FMT(a.price)}</span>
              <span className={`stat-num w-16 text-right ${cls(a.change_24h)}`}>
                {a.change_24h != null ? (a.change_24h > 0 ? '+' : '') + a.change_24h + '%' : '—'}</span>
              <span className="stat-num w-16 text-right text-muted text-xs">{VOL(a.volume_24h)}</span>
              <span className="stat-num w-12 text-right text-muted text-xs">{a.max_leverage}x</span>
            </div>
          ))}
          {!filtered.length && <div className="px-4 py-6 text-center text-muted text-sm">결과 없음</div>}
        </div>
        <div className="px-4 py-2 border-t border-border text-[10px] text-muted flex gap-3">
          <span>↑↓ 이동</span><span>Enter 선택</span><span>★ 즐겨찾기</span><span>거래량순 정렬</span>
        </div>
      </div>
    </div>
  );
}

export { useFavs, VOL };
