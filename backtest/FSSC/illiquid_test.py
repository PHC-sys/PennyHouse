# -*- coding: utf-8 -*-
"""
유동성 없는 자산에서 전략이 진짜 먹히나 — 제대로 검증.
illiquid 페어 풀링 + 발견자룰(R1, 페어 선별편향 없음) + 체결비용(슬리피지) 스윕.
질문: thin market 비효율이 실제 엣지인가, 슬리피지 후엔 죽나.
실행: python backtest/FSSC/illiquid_test.py
"""
import sys
import os
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from governance.engine import fetch_universe
from governance.engine.prices import fetch_candles, fetch_funding_history

DAYS = 110
W = 20
ENTRY = 50
CORR_MIN = 0.5
MAXHOLD = 15


def illiquid_universe(n=30):
    uni = [a for a in fetch_universe() if a.get('open_interest') and a.get('volume_24h')]
    uni = [a for a in uni if 0 < a['open_interest'] < 8e6 and a['volume_24h'] > 2e5]  # 얇지만 거래는 됨
    uni.sort(key=lambda a: a['open_interest'])
    return [(a['symbol'], a['open_interest']) for a in uni[:n]]


def load(symbols):
    R, Fd = {}, {}
    for s in symbols:
        c = fetch_candles(s, days=DAYS + 5, interval='1d')
        if c is not None and len(c) > 40:
            cl = c['close'].copy(); cl.index = cl.index.tz_localize(None)
            R[s] = cl.pct_change()
        f = fetch_funding_history(s, days=DAYS + 5)
        if f is not None and len(f):
            d = f['fundingRate'].resample('1D').sum(); d.index = d.index.tz_localize(None)
            Fd[s] = d
    return pd.DataFrame(R), pd.DataFrame(Fd)


def _beta(ya, xb):
    m = ~(np.isnan(xb) | np.isnan(ya))
    if m.sum() < 5:
        return None
    return float(np.linalg.lstsq(np.column_stack([np.ones(m.sum()), xb[m]]), ya[m], rcond=None)[0][1])


def R1(a, b, R, Fd):
    """발견자룰(고펀딩+MTM딥 진입 / 펀딩역전 청산), 베타헷지. 페어선별 없음."""
    idx = R.index.intersection(Fd.index)
    ra, rb, fa, fb = R[a].loc[idx], R[b].loc[idx], Fd[a].loc[idx], Fd[b].loc[idx]
    out, held, ei = [], 0, None
    for i in range(W, len(idx)):
        beta = _beta(ra.iloc[i - W:i].values, rb.iloc[i - W:i].values)
        if beta is None:
            continue
        hb = beta / max(abs(beta), 1)
        ret = ra.iloc[i] - hb * rb.iloc[i]
        carry = -(fa.iloc[i] - hb * fb.iloc[i]) * 365 * 100
        if np.isnan(ret) or np.isnan(carry):
            continue
        d = 1 if carry >= 0 else -1
        if held == 0:
            if abs(carry) > ENTRY and d * ret < 0:
                held, ei = d, i
        elif (held == 1 and carry < 0) or (held == -1 and carry > 0) or (i - ei >= MAXHOLD):
            pl = 0.0
            for j in range(ei + 1, i + 1):
                bj = _beta(ra.iloc[j - W:j].values, rb.iloc[j - W:j].values)
                if bj is None:
                    continue
                h = bj / max(abs(bj), 1)
                rj, fj = ra.iloc[j] - h * rb.iloc[j], -(fa.iloc[j] - h * fb.iloc[j])
                if not np.isnan(rj):
                    pl += held * (rj + fj)
            out.append(pl); held = 0
    return out


def main():
    liq = illiquid_universe(30)
    syms = [s for s, _ in liq]
    print(f'illiquid 종목 {len(syms)}: {[s.split(":")[-1] for s in syms[:12]]}... (OI<$8M)')
    R, Fd = load(syms)
    common = [s for s in syms if s in R.columns and s in Fd.columns and R[s].notna().sum() > 60]
    corr = R[common].corr()
    pairs = [(a, b) for a, b in combinations(common, 2) if corr.loc[a, b] >= CORR_MIN]
    print(f'데이터 {len(common)}종목 · 상관>{CORR_MIN} 페어 {len(pairs)}개')
    pool = []
    for a, b in pairs:
        pool += R1(a, b, R, Fd)
    pl = np.array([p for p in pool if not np.isnan(p)])
    if len(pl) < 8:
        print(f'트레이드 {len(pl)} (<8, 부족)'); return
    print(f'\n=== illiquid 풀링 (발견자룰, 베타헷지) — n={len(pl)} ===')
    print('  체결비용(왕복) 스윕: thin market 슬리피지 반영')
    for cost in (0, 0.005, 0.01, 0.015, 0.02, 0.03):
        x = pl - cost   # 트레이드당 왕복 비용 차감
        win, loss = x[x > 0], x[x < 0]
        pf = win.sum() / -loss.sum() if len(loss) else float('inf')
        print(f'  비용 {cost*100:>4.1f}%: 승률 {(x>0).mean()*100:3.0f}% | 평균 {x.mean()*100:+5.2f}% '
              f'중앙값 {np.median(x)*100:+5.2f}% | 총 {x.sum()*100:+5.0f}% | PF {pf:.2f}')
    print('\n  ※ 동일자산 아닌 프록시헷지라 슬리피지=4체결+재헷지. thin 자산 현실 비용 1~3%.')
    print('  판정: 현실 비용(~1-2%)에서도 중앙값>0 & PF>1.3 이면 진짜 엣지(소용량).')


if __name__ == '__main__':
    main()
