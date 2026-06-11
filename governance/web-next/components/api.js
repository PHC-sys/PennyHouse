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
