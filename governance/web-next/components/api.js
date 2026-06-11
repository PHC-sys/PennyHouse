// API 호출 헬퍼 (Next rewrites로 백엔드 프록시)
export async function api(path, opts) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const fmtPct = (v, sign = true) =>
  (sign && v > 0 ? '+' : '') + (v == null ? '—' : v.toFixed(1)) + '%';
export const fmtUsd = (v) => '$' + Math.round(v).toLocaleString();
export const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

// 동적 소수점: 큰 수는 적게, 작은 수는 유효숫자 위주
export function smartNum(v) {
  if (v == null || isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (a >= 1) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (a >= 0.01) return v.toFixed(4);
  if (a > 0) return v.toPrecision(4);   // 0.001038 같은 작은 비율
  return '0';
}
