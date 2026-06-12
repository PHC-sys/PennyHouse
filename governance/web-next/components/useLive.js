'use client';
import { useEffect, useRef, useState } from 'react';

// dev(:3010)는 백엔드(:8099)로, 그 외엔 동일 호스트
function wsBase() {
  if (process.env.NEXT_PUBLIC_WS) return process.env.NEXT_PUBLIC_WS;
  if (typeof window === 'undefined') return '';
  const { protocol, host } = window.location;
  if (host.includes('3010')) return 'ws://127.0.0.1:8099';
  return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}`;
}

/**
 * 라이브 가격 구독. symbols 배열을 주면 해당만, 빈/널이면 전체.
 * 반환: { prices: {sym: price}, flash: {sym: 'up'|'down'} }
 */
export function useLiveMids(symbols) {
  const [prices, setPrices] = useState({});
  const [flash, setFlash] = useState({});
  const prevRef = useRef({});
  const wsRef = useRef(null);
  const key = symbols ? symbols.join(',') : 'all';

  useEffect(() => {
    let alive = true;
    let retry;
    function connect() {
      let ws;
      try { ws = new WebSocket(wsBase() + '/ws/market'); }
      catch { return; }
      wsRef.current = ws;
      ws.onopen = () => { if (symbols?.length) ws.send(JSON.stringify({ symbols })); };
      ws.onmessage = (e) => {
        if (!alive) return;
        let d; try { d = JSON.parse(e.data); } catch { return; }
        if (!d.mids) return;
        const fl = {};
        setPrices((p) => {
          const next = { ...p };
          for (const [s, v] of Object.entries(d.mids)) {
            const old = prevRef.current[s];
            if (old != null && v !== old) fl[s] = v > old ? 'up' : 'down';
            prevRef.current[s] = v;
            next[s] = v;
          }
          return next;
        });
        if (Object.keys(fl).length) {
          setFlash((f) => ({ ...f, ...fl }));
          setTimeout(() => setFlash((f) => {
            const n = { ...f };
            for (const s of Object.keys(fl)) delete n[s];
            return n;
          }), 500);
        }
      };
      ws.onclose = () => { if (alive) retry = setTimeout(connect, 2000); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    }
    connect();
    return () => { alive = false; clearTimeout(retry); try { wsRef.current?.close(); } catch {} };
    // eslint-disable-next-line
  }, [key]);

  return { prices, flash };
}

/**
 * 포커스된 단일 자산의 라이브 ctx 구독 (펀딩/마크/OI/거래량).
 * 모달 열릴 때만 — 거래소 방식("보는 것만 구독").
 */
export function useAssetCtx(symbol) {
  const [ctx, setCtx] = useState(null);
  useEffect(() => {
    if (!symbol) return;
    setCtx(null);
    let alive = true, retry, current;
    function connect() {
      try { current = new WebSocket(wsBase() + '/ws/asset/' + encodeURIComponent(symbol)); }
      catch { return; }
      current.onmessage = (e) => {
        if (!alive) return;
        try { const d = JSON.parse(e.data); if (d.ctx) setCtx(d.ctx); } catch {}
      };
      current.onclose = () => { if (alive) retry = setTimeout(connect, 2000); };
      current.onerror = () => { try { current.close(); } catch {} };
    }
    connect();
    return () => { alive = false; clearTimeout(retry); try { current?.close(); } catch {} };
  }, [symbol]);
  return ctx;
}
