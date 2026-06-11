'use client';
import { useEffect, useRef } from 'react';
import { createChart, LineStyle, CrosshairMode } from 'lightweight-charts';

const BASE = {
  layout: { background: { color: 'transparent' }, textColor: '#7d8a9c', fontFamily: 'inherit' },
  grid: { vertLines: { color: '#141c28' }, horzLines: { color: '#141c28' } },
  rightPriceScale: { borderColor: '#1f2937' },
  timeScale: { borderColor: '#1f2937' },
  crosshair: { mode: CrosshairMode.Normal },
};

const dedupe = (arr) => {
  const seen = new Set(); const out = [];
  for (const p of arr || []) { if (seen.has(p.time)) continue; seen.add(p.time); out.push(p); }
  return out;
};

// 여러 라인 (백테스트 수익률) — 변경 시 통째로 재생성 (저빈도라 안전)
export function MultiLine({ lines, height = 300, logScale = false }) {
  const elRef = useRef(null);
  useEffect(() => {
    if (!elRef.current) return;
    const chart = createChart(elRef.current, { ...BASE, height,
      width: elRef.current.clientWidth,
      rightPriceScale: { mode: logScale ? 1 : 0, borderColor: '#1f2937' } });
    (lines || []).forEach((ln) => {
      const s = chart.addLineSeries({ color: ln.color, lineWidth: ln.width || 2,
        lineStyle: ln.dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false });
      s.setData(dedupe(ln.data));
    });
    chart.timeScale().fitContent();
    const ro = new ResizeObserver(() =>
      chart.applyOptions({ width: elRef.current.clientWidth }));
    ro.observe(elRef.current);
    return () => { ro.disconnect(); chart.remove(); };
  }, [lines, logScale, height]);
  return <div ref={elRef} style={{ height }} />;
}

// 캔들 — 차트/시리즈는 mount 시 생성, 데이터만 갱신 (StrictMode 안전)
export function Candles({ data, height = 360 }) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const sRef = useRef(null);
  useEffect(() => {
    if (!elRef.current) return;
    const chart = createChart(elRef.current, { ...BASE, height, width: elRef.current.clientWidth });
    chartRef.current = chart;
    sRef.current = chart.addCandlestickSeries({
      upColor: '#26d07c', downColor: '#f6465d', borderVisible: false,
      wickUpColor: '#26d07c', wickDownColor: '#f6465d' });
    const ro = new ResizeObserver(() =>
      chart.applyOptions({ width: elRef.current.clientWidth }));
    ro.observe(elRef.current);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; sRef.current = null; };
  }, [height]);
  useEffect(() => {
    if (sRef.current && data && data.length) {
      sRef.current.setData(dedupe(data));
      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);
  return <div ref={elRef} style={{ height }} />;
}

// 단일 라인 (NAV/펀딩/상대가격) — 실시간 갱신 대응
export function Line({ data, height = 200, color = '#5b8def', area = false }) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const sRef = useRef(null);
  useEffect(() => {
    if (!elRef.current) return;
    const chart = createChart(elRef.current, { ...BASE, height, width: elRef.current.clientWidth });
    chartRef.current = chart;
    sRef.current = area
      ? chart.addAreaSeries({ lineColor: color, topColor: color + '55',
          bottomColor: color + '05', lineWidth: 2 })
      : chart.addLineSeries({ color, lineWidth: 2 });
    const ro = new ResizeObserver(() =>
      chart.applyOptions({ width: elRef.current.clientWidth }));
    ro.observe(elRef.current);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; sRef.current = null; };
  }, [height, color, area]);
  useEffect(() => {
    if (sRef.current && data && data.length) {
      sRef.current.setData(dedupe(data));
      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);
  return <div ref={elRef} style={{ height }} />;
}
