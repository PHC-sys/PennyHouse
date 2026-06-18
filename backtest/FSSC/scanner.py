# -*- coding: utf-8 -*-
"""
FSSC 전 종목 스캐너 (전략 탐색 엔진) — 유동 상위 × 상관 페어 × 베타헷지 × 발견자룰.

목적: 4종목 데이터부족 한계를 넘어, 유동 페어 다수에서 트레이드를 풀링해
      전략의 통계적 유의성·거래가능성을 검증. (KR200 아티팩트인지 진짜인지)

1) HL 유동 상위 TOP_N (OI) 수집  2) 상관>CORR_MIN 페어  3) 베타헷지+R1  4) 풀링
실행: python backtest/FSSC/scanner.py
"""
import sys
import os
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from governance.engine import fetch_universe
from governance.engine.prices import fetch_candles, fetch_funding_history

TOP_N = 30
DAYS = 110
CORR_MIN = 0.5
W = 20
ENTRY = 30
MIN_TRADES = 4


def liquid_universe(n):
    uni = [a for a in fetch_universe() if a.get('open_interest')]
    uni.sort(key=lambda a: -a['open_interest'])
    return [(a['symbol'], a['open_interest']) for a in uni[:n]]


def load(symbols):
    R, Fd = {}, {}
    for s in symbols:
        c = fetch_candles(s, days=DAYS + 5, interval='1d')
        if c is not None and len(c) > 30:
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
    A = np.column_stack([np.ones(m.sum()), xb[m]])
    coef, *_ = np.linalg.lstsq(A, ya[m], rcond=None)
    return float(coef[1])


def backtest_pair(a, b, R, Fd):
    """Long a / Short β·b (카리부호로 동적 플립), 발견자룰. 일별 재헷지."""
    idx = R.index.intersection(Fd.index)
    ra, rb, fa, fb = R[a].loc[idx], R[b].loc[idx], Fd[a].loc[idx], Fd[b].loc[idx]
    n = len(idx)
    trades, held, ei = [], 0, None
    for i in range(W, n):
        beta = _beta(ra.iloc[i - W:i].values, rb.iloc[i - W:i].values)
        if beta is None:
            continue
        ret = ra.iloc[i] - beta * rb.iloc[i]
        carry = -(fa.iloc[i] - beta * fb.iloc[i]) * 365 * 100
        if np.isnan(ret) or np.isnan(carry):
            continue
        d = 1 if carry >= 0 else -1
        if held == 0:
            if abs(carry) > ENTRY and d * ret < 0:
                held, ei = d, i
        elif (held == 1 and carry < 0) or (held == -1 and carry > 0):
            pl = 0.0
            for j in range(ei + 1, i + 1):
                bj = _beta(ra.iloc[j - W:j].values, rb.iloc[j - W:j].values)
                if bj is None:
                    continue
                rj, fj = ra.iloc[j] - bj * rb.iloc[j], -(fa.iloc[j] - bj * fb.iloc[j])
                if not (np.isnan(rj) or np.isnan(fj)):
                    pl += held * (rj + fj)
            trades.append(pl)
            held = 0
    return trades


def main():
    liq = liquid_universe(TOP_N)
    syms = [s for s, _ in liq]
    oi = dict(liq)
    print(f'유동 상위 {TOP_N}: {[s.split(":")[-1] for s in syms[:12]]}...')
    R, Fd = load(syms)
    common = [s for s in syms if s in R.columns and s in Fd.columns and R[s].notna().sum() > 60]
    print(f'데이터 확보 {len(common)}종목. 상관 계산...')
    corr = R[common].corr()
    pairs = [(a, b, corr.loc[a, b]) for a, b in combinations(common, 2)
             if corr.loc[a, b] >= CORR_MIN]
    pairs.sort(key=lambda x: -x[2])
    print(f'상관>{CORR_MIN} 페어 {len(pairs)}개. 백테스트...')

    pool, per = [], []
    for a, b, cc in pairs:
        tr = backtest_pair(a, b, R, Fd)
        if len(tr) >= MIN_TRADES:
            arr = np.array(tr)
            per.append((f'{a.split(":")[-1]}/{b.split(":")[-1]}', round(cc, 2), len(arr),
                        round((arr > 0).mean() * 100), round(arr.sum() * 100, 1),
                        round(arr.min() * 100, 1), min(oi.get(a, 0), oi.get(b, 0))))
            pool += tr
    pool = np.array(pool)
    print(f'\n=== 풀링 (전 유동 페어, 발견자룰+베타헷지) ===')
    if len(pool):
        print(f'  총 트레이드 {len(pool)} | 승률 {(pool>0).mean()*100:.0f}% | '
              f'총 {pool.sum()*100:+.0f}% | 평균 {pool.mean()*100:+.2f}% | 최악 {pool.min()*100:+.1f}%')
    df = pd.DataFrame(per, columns=['페어', '상관', 'n', '승률%', '총%', '최악%', 'min_OI'])
    df = df.sort_values(['승률%', 'n'], ascending=False)
    print('\n=== 페어별 상위 12 (승률순) ===')
    with pd.option_context('display.width', 200):
        print(df.head(12).to_string(index=False))
    print(f'\n  분석 페어 {len(per)}개 · 풀 트레이드 {len(pool)}건 (4종목 5~9건과 비교).')


if __name__ == '__main__':
    main()
