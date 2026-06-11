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

function useChart(height) {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  useEffect(() => {
    const chart = createChart(elRef.current, { ...BASE, height,
      width: elRef.current.clientWidth });
    chartRef.current = chart;
    const ro = new ResizeObserver(() =>
      chart.applyOptions({ width: elRef.current.clientWidth }));
    ro.observe(elRef.current);
    return () => { ro.disconnect(); chart.remove(); };
  }, [height]);
  return [elRef, chartRef];
}

// 여러 라인 시리즈 (백테스트 수익률 곡선)
export function MultiLine({ lines, height = 300, logScale = false }) {
  const [elRef, chartRef] = useChart(height);
  const seriesRef = useRef([]);
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return;
    chart.applyOptions({ rightPriceScale: { mode: logScale ? 1 : 0,
      borderColor: '#1f2937' } });
    seriesRef.current.forEach((s) => chart.removeSeries(s));
    seriesRef.current = [];
    (lines || []).forEach((ln) => {
      const s = chart.addLineSeries({
        color: ln.color, lineWidth: ln.width || 2,
        lineStyle: ln.dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false, lastValueVisible: true,
      });
      s.setData(ln.data);
      seriesRef.current.push(s);
    });
    chart.timeScale().fitContent();
  }, [lines, logScale]);
  return <div ref={elRef} style={{ height }} />;
}

// 캔들 차트
export function Candles({ data, height = 360 }) {
  const [elRef, chartRef] = useChart(height);
  const sRef = useRef(null);
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return;
    if (!sRef.current) {
      sRef.current = chart.addCandlestickSeries({
        upColor: '#26d07c', downColor: '#f6465d', borderVisible: false,
        wickUpColor: '#26d07c', wickDownColor: '#f6465d',
      });
    }
    if (data && data.length) { sRef.current.setData(data); chart.timeScale().fitContent(); }
  }, [data]);
  return <div ref={elRef} style={{ height }} />;
}

// 단일 라인 (NAV, 펀딩, 상대가격)
export function Line({ data, height = 200, color = '#5b8def', area = false }) {
  const [elRef, chartRef] = useChart(height);
  const sRef = useRef(null);
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return;
    if (!sRef.current) {
      sRef.current = area
        ? chart.addAreaSeries({ lineColor: color, topColor: color + '55',
            bottomColor: color + '05', lineWidth: 2 })
        : chart.addLineSeries({ color, lineWidth: 2 });
    }
    if (data && data.length) {
      const seen = new Set(); const clean = [];
      for (const p of data) { if (seen.has(p.time)) continue; seen.add(p.time); clean.push(p); }
      sRef.current.setData(clean); chart.timeScale().fitContent();
    }
  }, [data, color, area]);
  return <div ref={elRef} style={{ height }} />;
}
