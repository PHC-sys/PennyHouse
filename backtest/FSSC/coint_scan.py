# -*- coding: utf-8 -*-
"""
FSSC 공적분 기반 통계적 차익거래 — 상관이 아니라 cointegration으로 페어 선별.
스프레드(잔차) 정상성/반감기 검정 → 공적분 페어만 → 잔차 z-score 평균회귀.
공적분 페어 vs 비공적분 풀링 비교. (상관필터 MR이 졌던 게 stat-arb를 잘못한 탓인지 확인)
실행: python backtest/FSSC/coint_scan.py
"""
import sys
import os
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner import liquid_universe, TOP_N  # noqa
from governance.engine.prices import fetch_candles, fetch_funding_history

DAYS = 110
CORR_MIN = 0.5
ZIN, ZOUT, MAXHOLD, ZW = 1.5, 0.4, 20, 25
HALFLIFE_MAX = 20     # 공적분 인정: 반감기 ≤ 이 일수
BCOEF_MAX = 0.93      # AR(1) 계수 < 이값 (강한 평균회귀)


def load(symbols):
    P, R, Fd = {}, {}, {}
    for s in symbols:
        c = fetch_candles(s, days=DAYS + 5, interval='1d')
        if c is not None and len(c) > 40:
            cl = c['close'].copy(); cl.index = cl.index.tz_localize(None)
            P[s] = cl; R[s] = cl.pct_change()
        f = fetch_funding_history(s, days=DAYS + 5)
        if f is not None and len(f):
            d = f['fundingRate'].resample('1D').sum(); d.index = d.index.tz_localize(None)
            Fd[s] = d
    return pd.DataFrame(P), pd.DataFrame(R), pd.DataFrame(Fd)


def coint(pa, pb):
    """가격레벨 OLS → 잔차. AR(1) 반감기로 평균회귀 강도. Returns (beta, res_series, half, b)."""
    df = pd.concat([pa, pb], axis=1).dropna()
    if len(df) < 40:
        return None
    y, x = df.iloc[:, 0].values, df.iloc[:, 1].values
    A = np.column_stack([np.ones(len(x)), x])
    a0, beta = np.linalg.lstsq(A, y, rcond=None)[0]
    res = y - a0 - beta * x
    r0, r1 = res[:-1], res[1:]
    b = np.linalg.lstsq(np.column_stack([np.ones(len(r0)), r0]), r1, rcond=None)[0][1]
    half = -np.log(2) / np.log(b) if 0 < b < 1 else np.inf
    return beta, pd.Series(res, index=df.index), half, b


def mr_trades(res, ra, rb, beta, fa, fb):
    """잔차 z-score 평균회귀. z=(res−SMA)/STD. 진입 |z|>ZIN(반대방향), 청산 |z|<ZOUT."""
    z = (res - res.rolling(ZW).mean()) / res.rolling(ZW).std()
    idx = z.index
    out, held, ei = [], 0, None
    for i in range(1, len(idx)):
        zi = z.iloc[i]
        if np.isnan(zi):
            continue
        t = idx[i]
        if held == 0:
            if abs(zi) > ZIN:
                held, ei = (-1 if zi > 0 else 1), i   # 비싸면(z>0) 스프레드 숏
        elif abs(zi) < ZOUT or (i - ei >= MAXHOLD) or (held == 1 and zi > 0) or (held == -1 and zi < 0):
            pl = 0.0
            for j in range(ei + 1, i + 1):
                tj = idx[j]
                if tj in ra.index and tj in rb.index:
                    rj = ra.get(tj, np.nan) - beta * rb.get(tj, np.nan) / max(abs(beta), 1)  # 정규화 헷지
                    fj = -(fa.get(tj, 0) - beta * fb.get(tj, 0) / max(abs(beta), 1))
                    if not np.isnan(rj):
                        pl += held * (rj + fj)
            out.append(pl)
            held = 0
    return out


def pool_stats(name, pl):
    pl = np.array([p for p in pl if not np.isnan(p)])
    if len(pl) < 8:
        print(f'  {name:16} n={len(pl)} (<8)'); return
    win = pl[pl > 0]; loss = pl[pl < 0]
    pf = win.sum() / -loss.sum() if len(loss) else float('inf')
    print(f'  {name:16} n={len(pl):4d} 승률 {(pl>0).mean()*100:3.0f}% | 평균 {pl.mean()*100:+5.2f}% '
          f'중앙값 {np.median(pl)*100:+5.2f}% | 총 {pl.sum()*100:+5.0f}% | PF {pf:.2f} | 최악 {pl.min()*100:+.1f}%')


def main():
    syms = [s for s, _ in liquid_universe(TOP_N)]
    P, R, Fd = load(syms)
    common = [s for s in syms if s in P.columns and s in Fd.columns and P[s].notna().sum() > 60]
    corr = R[common].corr()
    pairs = [(a, b) for a, b in combinations(common, 2) if corr.loc[a, b] >= CORR_MIN]
    print(f'유동 {len(common)}종목 · 상관>{CORR_MIN} 페어 {len(pairs)}개')

    coint_pl, noncoint_pl, ncoint = [], [], 0
    coint_list = []
    for a, b in pairs:
        c = coint(P[a], P[b])
        if c is None:
            continue
        beta, res, half, bco = c
        tr = mr_trades(res, R[a], R[b], beta, Fd[a], Fd[b])
        is_coint = (half <= HALFLIFE_MAX and bco < BCOEF_MAX)
        if is_coint:
            ncoint += 1; coint_pl += tr
            coint_list.append((f'{a.split(":")[-1]}/{b.split(":")[-1]}', round(half, 1), round(corr.loc[a, b], 2)))
        else:
            noncoint_pl += tr
    print(f'공적분(반감기≤{HALFLIFE_MAX}일 & AR<{BCOEF_MAX}) 페어 {ncoint}개\n')
    print('=== 잔차 z-score 평균회귀 풀링 ===')
    pool_stats('공적분 페어', coint_pl)
    pool_stats('비공적분 페어', noncoint_pl)
    if coint_list:
        print('\n공적분 페어(반감기·상관):')
        for nm, h, cc in sorted(coint_list, key=lambda x: x[1])[:15]:
            print(f'  {nm:16} 반감기 {h}일  상관 {cc}')


if __name__ == '__main__':
    main()
