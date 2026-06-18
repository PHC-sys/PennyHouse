# -*- coding: utf-8 -*-
"""
FSSC 다중 룰 전략 탐색 — 유동 상관 페어 × 여러 룰 × 베타헷지 → 풀링 비교.
이기는 룰의 '본질'(수익 출처=카리 vs 가격, 보유기간, 비대칭)까지 분해.
실행: python backtest/FSSC/multi_rule_scan.py
"""
import sys
import os
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner import liquid_universe, load, _beta, TOP_N, CORR_MIN, W  # noqa

ENTRY = 30
ZIN, ZOUT, MAXHOLD = 1.5, 0.5, 15


def spread(a, b, R, Fd):
    idx = R.index.intersection(Fd.index)
    ra, rb, fa, fb = R[a].loc[idx], R[b].loc[idx], Fd[a].loc[idx], Fd[b].loc[idx]
    ret, fund = [], []
    for i in range(len(idx)):
        beta = _beta(ra.iloc[i - W:i].values, rb.iloc[i - W:i].values) if i >= W else None
        if beta is None:
            ret.append(np.nan); fund.append(np.nan); continue
        ret.append(ra.iloc[i] - beta * rb.iloc[i])
        fund.append(-(fa.iloc[i] - beta * fb.iloc[i]))
    return pd.Series(ret, index=idx), pd.Series(fund, index=idx)


def R1(ret, fund):  # 펀딩 페이드 (발견자룰)
    carry = fund * 365 * 100
    out, held, ei = [], 0, None
    for i in range(1, len(ret)):
        c, r = carry.iloc[i], ret.iloc[i]
        if np.isnan(c):
            continue
        d = 1 if c >= 0 else -1
        if held == 0:
            if abs(c) > ENTRY and d * r < 0:
                held, ei = d, i
        elif (held == 1 and c < 0) or (held == -1 and c > 0) or (i - ei >= MAXHOLD):
            pr = sum(held * ret.iloc[j] for j in range(ei + 1, i + 1))
            ca = sum(held * fund.iloc[j] for j in range(ei + 1, i + 1))
            out.append((pr + ca, ca, pr, i - ei)); held = 0
    return out


def Zrule(ret, fund, mode, fund_filter=False):  # MR / MOM (z-score)
    S = ret.cumsum()
    z = (S - S.rolling(W).mean()) / S.rolling(W).std()
    carry = fund * 365 * 100
    out, held, ei = [], 0, None
    for i in range(1, len(ret)):
        zi = z.iloc[i]
        if np.isnan(zi):
            continue
        if held == 0:
            if abs(zi) > ZIN:
                d = int(-np.sign(zi)) if mode == 'MR' else int(np.sign(zi))
                if fund_filter and not (d * carry.iloc[i] > 0):  # 카리 순풍만
                    continue
                held, ei = d, i
        elif abs(zi) < ZOUT or (i - ei >= MAXHOLD) or \
                (mode == 'MR' and ((held == 1 and zi > 0) or (held == -1 and zi < 0))):
            pr = sum(held * ret.iloc[j] for j in range(ei + 1, i + 1))
            ca = sum(held * fund.iloc[j] for j in range(ei + 1, i + 1))
            out.append((pr + ca, ca, pr, i - ei)); held = 0
    return out


def report(name, pool):
    if len(pool) < 8:
        print(f'  {name:18} 트레이드 {len(pool)} (<8, 평가보류)'); return
    tot = np.array([p[0] for p in pool])
    ca = np.array([p[1] for p in pool]); pr = np.array([p[2] for p in pool])
    hold = np.array([p[3] for p in pool])
    sharpe = tot.mean() / tot.std() * np.sqrt(len(tot)) if tot.std() > 0 else 0
    pf = tot[tot > 0].sum() / -tot[tot < 0].sum() if (tot < 0).any() else float('inf')
    print(f'  {name:18} n={len(tot):4d} 승률 {(tot>0).mean()*100:3.0f}% | '
          f'총 {tot.sum()*100:+6.0f}% 평균 {tot.mean()*100:+5.2f}% 최악 {tot.min()*100:+6.1f}% | '
          f'PF {pf:4.2f} t {sharpe:+4.1f} | 보유 {hold.mean():3.1f}일 | '
          f'카리 {ca.sum()*100:+5.0f}% 가격 {pr.sum()*100:+5.0f}%')


def main():
    syms = [s for s, _ in liquid_universe(TOP_N)]
    R, Fd = load(syms)
    common = [s for s in syms if s in R.columns and s in Fd.columns and R[s].notna().sum() > 60]
    corr = R[common].corr()
    pairs = [(a, b) for a, b in combinations(common, 2) if corr.loc[a, b] >= CORR_MIN]
    print(f'유동 {len(common)}종목 · 상관>{CORR_MIN} 페어 {len(pairs)}개\n')

    pools = {'R1 펀딩페이드': [], 'R2 가격MR': [], 'R3 가격MOM': [], 'R2f 가격MR+카리': []}
    for a, b in pairs:
        ret, fund = spread(a, b, R, Fd)
        pools['R1 펀딩페이드'] += R1(ret, fund)
        pools['R2 가격MR'] += Zrule(ret, fund, 'MR')
        pools['R3 가격MOM'] += Zrule(ret, fund, 'MOM')
        pools['R2f 가격MR+카리'] += Zrule(ret, fund, 'MR', fund_filter=True)

    print('=== 룰별 풀링 (전 유동 페어, 베타헷지) ===')
    print('  PF=손익비, t=대략 유의성(>2 유의), 보유=평균일')
    for nm, pl in pools.items():
        report(nm, pl)


if __name__ == '__main__':
    main()
