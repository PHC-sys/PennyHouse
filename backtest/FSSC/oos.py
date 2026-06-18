# -*- coding: utf-8 -*-
"""
공적분 stat-arb 아웃오브샘플 검증 — 선별편향(룩어헤드) 제거.
학습기간: 공적분 페어 선별 + β·잔차통계 추정. 테스트기간: 그걸로만 거래.
실행: python backtest/FSSC/oos.py
"""
import sys
import os
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner import liquid_universe, TOP_N
from coint_scan import load, CORR_MIN, ZIN, ZOUT, MAXHOLD, HALFLIFE_MAX, BCOEF_MAX


def ols(pa, pb):
    df = pd.concat([pa, pb], axis=1).dropna()
    if len(df) < 30:
        return None
    y, x = df.iloc[:, 0].values, df.iloc[:, 1].values
    a0, beta = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y, rcond=None)[0]
    res = pd.Series(y - a0 - beta * x, index=df.index)
    r0, r1 = res.values[:-1], res.values[1:]
    b = np.linalg.lstsq(np.column_stack([np.ones(len(r0)), r0]), r1, rcond=None)[0][1]
    half = -np.log(2) / np.log(b) if 0 < b < 1 else np.inf
    return a0, beta, res, half, b


def trades(z, ra, rb, fa, fb, beta):
    idx = z.index
    hedge = beta / max(abs(beta), 1)
    out, held, ei = [], 0, None
    for i in range(1, len(idx)):
        zi = z.iloc[i]
        if np.isnan(zi):
            continue
        if held == 0:
            if abs(zi) > ZIN:
                held, ei = (-1 if zi > 0 else 1), i
        elif abs(zi) < ZOUT or (i - ei >= MAXHOLD) or (held == 1 and zi > 0) or (held == -1 and zi < 0):
            pl = 0.0
            for j in range(ei + 1, i + 1):
                tj = idx[j]
                rj = ra.get(tj, np.nan) - hedge * rb.get(tj, np.nan)
                fj = -(fa.get(tj, 0) - hedge * fb.get(tj, 0))
                if not np.isnan(rj):
                    pl += held * (rj + fj)
            out.append(pl); held = 0
    return out


def run(frac, P, R, Fd, common):
    n = len(P)
    cut = int(n * frac)
    tr_idx, te_idx = P.index[:cut], P.index[cut:]
    corr = R.loc[tr_idx, common].corr()
    pairs = [(a, b) for a, b in combinations(common, 2) if corr.loc[a, b] >= CORR_MIN]
    pool, sel = [], 0
    for a, b in pairs:
        c = ols(P[a].loc[tr_idx], P[b].loc[tr_idx])    # 학습: β·잔차통계
        if c is None:
            continue
        a0, beta, res_tr, half, bco = c
        if not (half <= HALFLIFE_MAX and bco < BCOEF_MAX):
            continue
        sel += 1
        mu, sd = res_tr.mean(), res_tr.std()
        # 테스트: 학습 β·mu·sd로 잔차·z (테스트 데이터 미사용 추정)
        res_te = P[a].loc[te_idx] - a0 - beta * P[b].loc[te_idx]
        z = (res_te - mu) / sd
        pool += trades(z, R[a].loc[te_idx], R[b].loc[te_idx], Fd[a].loc[te_idx], Fd[b].loc[te_idx], beta)
    pl = np.array([p for p in pool if not np.isnan(p)])
    lbl = f'train {int(frac*100)}% / test {100-int(frac*100)}%'
    if len(pl) < 6:
        print(f'  {lbl}: 선별 {sel}페어, 테스트 트레이드 {len(pl)} (<6, 부족)'); return
    win, loss = pl[pl > 0], pl[pl < 0]
    pf = win.sum() / -loss.sum() if len(loss) else float('inf')
    print(f'  {lbl}: 선별 {sel}페어 | 테스트 n={len(pl)} 승률 {(pl>0).mean()*100:.0f}% | '
          f'평균 {pl.mean()*100:+.2f}% 중앙값 {np.median(pl)*100:+.2f}% | 총 {pl.sum()*100:+.0f}% | '
          f'PF {pf:.2f} | 최악 {pl.min()*100:+.1f}%')


def main():
    syms = [s for s, _ in liquid_universe(TOP_N)]
    P, R, Fd = load(syms)
    common = [s for s in syms if s in P.columns and s in Fd.columns and P[s].notna().sum() > 80]
    print(f'유동 {len(common)}종목 · {len(P)}일\n=== 아웃오브샘플 (학습선별 → 테스트거래) ===')
    for frac in (0.5, 0.6, 0.7):
        run(frac, P, R, Fd, common)
    print('\n  중앙값>0 & 여러 split 일관되면 = 진짜. 한 split만 좋으면 의심.')


if __name__ == '__main__':
    main()
