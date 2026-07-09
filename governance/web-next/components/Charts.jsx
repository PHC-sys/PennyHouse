'use client';
import { useEffect, useRef } from 'react';
import { createChart, LineStyle, CrosshairMode } from 'lightweight-charts';
import { smartNum } from '@/components/api';

const BASE = {
  layout: { background: { color: 'transparent' }, textColor: '#7d8a9c', fontFamily: 'inherit' },
  grid: { vertLines: { color: '#141c28' }, horzLines: { color: '#141c28' } },
  rightPriceScale: { borderColor: '#1f2937' },
  timeScale: { borderColor: '#1f2937', rightOffset: 6, minBarSpacing: 0.5,
    timeVisible: true, secondsVisible: false },  // 분/시간봉이면 시간까지 표시
  crosshair: { mode: CrosshairMode.Normal },
  localization: { priceFormatter: smartNum },  // 동적 소수점 (축·툴팁)
  handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
  handleScale: { mouseWheel: true, pinch: true,
    axisPressedMouseMove: { time: true, price: true } },
};

const dedupe = (arr) => {
  const seen = new Set(); const out = [];
  for (const p of arr || []) { if (seen.has(p.time)) continue; seen.add(p.time); out.push(p); }
  return out;
};

// 리사이즈 옵저버 — DOM 노드를 캡처해서 사용 (언마운트 후 null 참조 방지)
function attachResize(el, chart) {
  const ro = new ResizeObserver(() => {
    if (el && el.isConnected) chart.applyOptions({ width: el.clientWidth });
  });
  ro.observe(el);
  return ro;
}

// 여러 라인 (백테스트 수익률) — 변경 시 통째로 재생성 (저빈도라 안전)
export function MultiLine({ lines, height = 300, logScale = false }) {
  const elRef = useRef(null);
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const chart = createChart(el, { ...BASE, height, width: el.clientWidth,
      rightPriceScale: { mode: logScale ? 1 : 0, borderColor: '#1f2937' } });
    (lines || []).forEach((ln) => {
      const s = chart.addLineSeries({ color: ln.color, lineWidth: ln.width || 2,
        lineStyle: ln.dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false });
      s.setData(dedupe(ln.data));
    });
    chart.timeScale().fitContent();
    const ro = attachResize(el, chart);
    return () => { ro.disconnect(); chart.remove(); };
  }, [lines, logScale, height]);
  return <div ref={elRef} style={{ height }} />;
}

// 캔들 — 차트/시리즈는 mount 시 생성, 데이터만 갱신 (StrictMode 안전)
// onCrosshair: 호버 콜백 / livePrice: 진행 봉 실시간 갱신 / intervalSec: 새 봉 자동 생성
export function Candles({ data, height = 360, onCrosshair, livePrice, intervalSec }) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const sRef = useRef(null);
  const lastBarRef = useRef(null);
  const cbRef = useRef(onCrosshair);
  cbRef.current = onCrosshair;
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const chart = createChart(el, { ...BASE, height, width: el.clientWidth });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: '#26d07c', downColor: '#f6465d', borderVisible: false,
      wickUpColor: '#26d07c', wickDownColor: '#f6465d' });
    sRef.current = series;
    chart.subscribeCrosshairMove((param) => {
      if (!cbRef.current) return;
      const p = param.seriesData?.get(series);
      cbRef.current(p ? { time: param.time, ...p } : null);
    });
    const ro = attachResize(el, chart);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; sRef.current = null; };
  }, [height]);
  useEffect(() => {
    if (sRef.current && data && data.length) {
      const clean = dedupe(data);
      sRef.current.setData(clean);
      lastBarRef.current = { ...clean[clean.length - 1] };
      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);
  // 라이브 가격으로 마지막 봉 갱신 + 기간 넘어가면 새 봉 자동 생성
  useEffect(() => {
    const lb = lastBarRef.current;
    if (!sRef.current || !lb || livePrice == null) return;
    const now = Math.floor(Date.now() / 1000);
    let bar;
    if (intervalSec && now >= lb.time + intervalSec) {
      // 새 봉 시작 (경계에 정렬)
      const newTime = lb.time + intervalSec * Math.floor((now - lb.time) / intervalSec);
      bar = { time: newTime, open: livePrice, high: livePrice, low: livePrice, close: livePrice };
    } else {
      bar = { ...lb, close: livePrice,
        high: Math.max(lb.high, livePrice), low: Math.min(lb.low, livePrice) };
    }
    lastBarRef.current = bar;
    try { sRef.current.update(bar); } catch {}
  }, [livePrice, intervalSec]);
  return <div ref={elRef} style={{ height }} />;
}

// 스파크라인 (마켓 타일용 — 축/그리드 없음, 색은 등락 따라)
export function Spark({ data, height = 48, up = true }) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const sRef = useRef(null);
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const color = up ? '#26d07c' : '#f6465d';
    const chart = createChart(el, {
      layout: { background: { color: 'transparent' }, textColor: 'transparent' },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false }, leftPriceScale: { visible: false },
      timeScale: { visible: false }, crosshair: { mode: 0 },
      handleScroll: false, handleScale: false,
      height, width: el.clientWidth,
    });
    chartRef.current = chart;
    sRef.current = chart.addAreaSeries({ lineColor: color, topColor: color + '40',
      bottomColor: color + '00', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
    const ro = attachResize(el, chart);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; sRef.current = null; };
  }, [height, up]);
  useEffect(() => {
    if (sRef.current && data && data.length) {
      sRef.current.setData(dedupe(data));
      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);
  return <div ref={elRef} style={{ height }} />;
}

// 단일 라인 (NAV/펀딩/상대가격) — 실시간 갱신 + 선택적 기준선(baseline)
export function Line({ data, height = 200, color = '#5b8def', area = false, baseline }) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const sRef = useRef(null);
  const plRef = useRef(null);
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const chart = createChart(el, { ...BASE, height, width: el.clientWidth });
    chartRef.current = chart;
    sRef.current = area
      ? chart.addAreaSeries({ lineColor: color, topColor: color + '55',
          bottomColor: color + '05', lineWidth: 2 })
      : chart.addLineSeries({ color, lineWidth: 2 });
    const ro = attachResize(el, chart);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; sRef.current = null; plRef.current = null; };
  }, [height, color, area]);
  useEffect(() => {
    if (!sRef.current) return;
    sRef.current.setData(dedupe(data || []));   // 빈 데이터면 클리어 (이전 차트 stale 방지)
    if (data && data.length) chartRef.current?.timeScale().fitContent();
  }, [data]);
  // 기준선 (예: 현재 펀딩값)
  useEffect(() => {
    if (!sRef.current) return;
    if (plRef.current) { try { sRef.current.removePriceLine(plRef.current); } catch {} plRef.current = null; }
    if (baseline && baseline.value != null) {
      plRef.current = sRef.current.createPriceLine({
        price: baseline.value, color: baseline.color || '#f6465d',
        lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: baseline.label || '' });
    }
  }, [baseline, data]);
  return <div ref={elRef} style={{ height }} />;
}
