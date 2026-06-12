'use client';
import { useEffect, useState } from 'react';
import { api, cls, smartNum } from '@/components/api';
import { Candles, Line } from '@/components/Charts';
import AssetPicker, { VOL } from '@/components/AssetPicker';
import { useLiveMids } from '@/components/useLive';

const INTERVALS = ['1h', '4h', '1d', '1w'];
const INTERVAL_SEC = { '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800 };
const FMT = smartNum;

export default function AssetModal({ asset, onClose }) {
  const [interval, setInterval] = useState('1d');
  const [days, setDays] = useState(180);
  const [candles, setCandles] = useState([]);
  const [funding, setFunding] = useState([]);
  const [rel, setRel] = useState([]);
  const [relAsset, setRelAsset] = useState({ symbol: asset.display === 'BTC' ? 'ETH' : 'BTC',
    display: asset.display === 'BTC' ? 'ETH' : 'BTC' });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [hover, setHover] = useState(null);
  const [vol, setVol] = useState(null);

  const sym = asset.symbol;
  // 라이브: 이 자산 + 비교 자산만 구독
  const { prices: live, flash } = useLiveMids([sym, relAsset.symbol]);
  const livePrice = live[sym];
  const prevDay = asset.change_24h != null ? asset.price / (1 + asset.change_24h / 100) : null;
  const liveChange = (prevDay && livePrice) ? (livePrice / prevDay - 1) * 100 : asset.change_24h;

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !pickerOpen) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, pickerOpen]);

  useEffect(() => {
    api(`/api/prices/${sym}?days=${days}&interval=${interval}`)
      .then((d) => setCandles(d.candles)).catch(() => setCandles([]));
  }, [sym, days, interval]);
  useEffect(() => {
    api(`/api/spark/${sym}?days=30`).then((d) => setVol(d.volatility)).catch(() => {});
  }, [sym]);
  useEffect(() => {  // 펀딩 — 90일 고정(빠른 로딩, 캐시). 기간과 분리
    setFunding([]);
    api(`/api/funding/${sym}?days=90`).then((d) => setFunding(d.series)).catch(() => setFunding([]));
  }, [sym]);
  useEffect(() => {
    const bSym = relAsset.symbol;
    api(`/api/relative?a=${encodeURIComponent(sym)}&b=${encodeURIComponent(bSym)}&days=${days}&interval=${interval}`)
      .then((d) => setRel(d.series)).catch(() => setRel([]));
  }, [sym, relAsset, days, interval]);

  const h = hover;
  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}>
      <div className="bg-surface border border-border rounded-2xl shadow-glow w-full max-w-[1100px]
        max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* 헤더 */}
        <div className="sticky top-0 bg-surface/95 backdrop-blur border-b border-border px-5 py-3
          flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{asset.display}</span>
            <span className="text-[10px] uppercase text-muted border border-border rounded px-1.5 py-0.5">
              {asset.sub || asset.category}</span>
          </div>
          <div className={`stat-num text-lg px-1 -mx-1 ${flash[sym] === 'up' ? 'flash-up'
            : flash[sym] === 'down' ? 'flash-down' : ''}`}>${FMT(livePrice ?? asset.price)}</div>
          <div className={`stat-num font-semibold ${cls(liveChange)}`}>
            {liveChange > 0 ? '+' : ''}{liveChange?.toFixed(2)}% <span className="text-[10px] text-muted">24h</span>
          </div>
          <div className="flex gap-4 text-xs text-muted ml-2 flex-wrap">
            <span>펀딩 <span className={cls(-asset.funding_annual)}>{asset.funding_annual}%</span></span>
            <span>변동성 <span className="text-fg">{vol != null ? (vol * 100).toFixed(1) + '%' : '—'}</span></span>
            <span>24h Vol <span className="text-fg">${VOL(asset.volume_24h)}</span></span>
            <span>OI <span className="text-fg">${VOL(asset.open_interest)}</span></span>
            <span>최대 {asset.max_leverage}x</span>
          </div>
          <button className="ml-auto btn-ghost py-1" onClick={onClose}>닫기 ✕</button>
        </div>

        <div className="p-5 space-y-4">
          {/* 캔들 + OHLC 리드아웃 */}
          <div>
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <h4 className="text-sm font-semibold">가격 차트 <span className="text-muted text-[10px]">시간 UTC</span></h4>
              <div className="flex gap-1.5">
                {INTERVALS.map((iv) => (
                  <span key={iv} className={`chip ${interval === iv ? 'chip-active' : ''}`}
                    onClick={() => setInterval(iv)}>{iv}</span>))}
              </div>
              <select className="input py-1 text-xs ml-auto" value={days}
                onChange={(e) => setDays(+e.target.value)}>
                {[30, 90, 180, 365, 730].map((d) => <option key={d} value={d}>{d}일</option>)}
              </select>
            </div>
            {h && (
              <div className="flex gap-4 text-[11px] stat-num mb-1 text-muted">
                <span>O <span className="text-fg">{FMT(h.open)}</span></span>
                <span>H <span className="pos">{FMT(h.high)}</span></span>
                <span>L <span className="neg">{FMT(h.low)}</span></span>
                <span>C <span className={h.close >= h.open ? 'pos' : 'neg'}>{FMT(h.close)}</span></span>
              </div>
            )}
            <Candles data={candles} height={340} onCrosshair={setHover}
              livePrice={livePrice} intervalSec={INTERVAL_SEC[interval]} />
          </div>

          {/* 펀딩 + 상대가격 */}
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <h4 className="text-sm font-semibold mb-1">펀딩비 추이
                <span className="text-muted text-[10px] ml-1">최근 90일 · 시간별 연환산 % · UTC</span></h4>
              <div className="text-[10px] text-muted mb-1">
                ━ 점선 = 현재 펀딩 <span className={cls(-asset.funding_annual)}>{asset.funding_annual}%</span>
                <span className="ml-1">(헤더와 동일, 차트는 과거 추이)</span></div>
              <Line data={funding} height={186} color="#f0b90b" area
                baseline={{ value: asset.funding_annual, label: '현재', color: '#e74c3c' }} />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-2">
                <h4 className="text-sm font-semibold">상대가격</h4>
                <span className="text-brand text-xs font-semibold">{asset.display} /</span>
                <button className="btn-ghost py-0.5 px-2 text-xs flex items-center gap-1"
                  onClick={() => setPickerOpen(true)}>
                  {relAsset.display} <span className="text-muted">▾</span></button>
              </div>
              <Line data={rel} height={200} color="#a855f7" />
            </div>
          </div>
        </div>
      </div>
      <AssetPicker open={pickerOpen} onClose={() => setPickerOpen(false)}
        onSelect={(a) => setRelAsset(a)} title="비교 자산 선택" />
    </div>
  );
}
