# -*- coding: utf-8 -*-
"""
FSSC 전략 룰 비교 — "더 나은 전략" 탐색. 베타헷지 스프레드 위에서 룰만 바꿔 비교.

R1 발견자룰 : 진입 |카리|>th & MTM딥 / 청산 펀딩역전
R2 가격MR   : 진입 |가격스프레드 z|>Zin (평균회귀) / 청산 z→0  (펀딩 무시)
R3 펀딩MR   : 진입 |카리 z|>Zin / 청산 카리 z→0
R4 결합     : 가격z & 카리 둘 다 극단 + MTM딥

질문: 엣지가 펀딩 신호인가 그냥 가격 평균회귀인가? 어느 룰이 최고인가?
실행: python backtest/FSSC/strategy_compare.py
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy_search import load  # noqa

W = 20
STRUCTS = {
    'DRAM/KR200':      (['DRAM'], ['KR200']),
    'KR200/SKHX+DRAM': (['KR200'], ['SKHX', 'DRAM']),
    'chips/DRAM':      (['SKHX', 'SMSN'], ['DRAM']),
    'chips/KR200':     (['SKHX', 'SMSN'], ['KR200']),
}


def series(long, short, R, Fd):
    """베타헷지 스프레드의 일별 [가격손익, 펀딩손익] (롱바스켓 +1 / 숏 −β)."""
    idx = R.index.intersection(Fd.index)
    R, Fd = R.loc[idx], Fd.loc[idx]
    sr, fr = [], []
    for i in range(len(idx)):
        if i < W:
            sr.append(np.nan); fr.append(np.nan); continue
        Xs = R[short].iloc[i - W:i].values
        yl = R[long].mean(axis=1).iloc[i - W:i].values
        coef, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(Xs)), Xs]), yl, rcond=None)
        w = {a: 1.0 / len(long) for a in long}
        for a, b in zip(short, coef[1:]):
            w[a] = -float(b)
        sr.append(sum(w[a] * R[a].iloc[i] for a in long + short))
        fr.append(-sum(w[a] * Fd[a].iloc[i] for a in long + short))
    return pd.Series(sr, index=idx), pd.Series(fr, index=idx)


def stats(tr):
    if len(tr) < 4:
        return None
    tr = np.array(tr)
    return len(tr), round((tr > 0).mean() * 100), round(tr.sum() * 100, 1), round(tr.min() * 100, 1)


def r1(sr, fr, th=30):
    carry = fr * 365 * 100
    days = list(sr.index); held, ei = 0, None; out = []
    for i in range(1, len(days)):
        c, r = carry.iloc[i], sr.iloc[i]
        if np.isnan(c):
            continue
        d = 1 if c >= 0 else -1
        if held == 0:
            if abs(c) > th and d * r < 0:
                held, ei = d, i
        elif (held == 1 and c < 0) or (held == -1 and c > 0):
            out.append(sum(held * (sr.iloc[j] + fr.iloc[j]) for j in range(ei + 1, i + 1))); held = 0
    return out


def zscore_mr(sig, sr, fr, Zin=1.5, Zout=0.3):
    """z>Zin면 숏(평균회귀), z<−Zin면 롱. z→0 청산. sig=z 만들 시계열."""
    S = sig.cumsum()
    z = (S - S.rolling(W).mean()) / S.rolling(W).std()
    days = list(sr.index); held, ei = 0, None; out = []
    for i in range(1, len(days)):
        zi = z.iloc[i]
        if np.isnan(zi):
            continue
        if held == 0:
            if abs(zi) > Zin:
                held, ei = (-1 if zi > 0 else 1), i   # 비싸면 숏, 싸면 롱
        elif abs(zi) < Zout or (held == 1 and zi > 0) or (held == -1 and zi < 0):
            out.append(sum(held * (sr.iloc[j] + fr.iloc[j]) for j in range(ei + 1, i + 1))); held = 0
    return out


def main():
    R, Fd = load()[0], load()[1]
    print(f'\n[전략 룰 비교] 베타헷지 · 롤링{W}일 · 1x · 수수료 미반영')
    print('  %-17s %-12s %3s %6s %7s %7s' % ('구조', '룰', 'n', '승률%', '총%', '최악%'))
    for nm, (lo, sh) in STRUCTS.items():
        sr, fr = series(lo, sh, R, Fd)
        runs = {
            'R1 발견자룰': r1(sr, fr),
            'R2 가격MR': zscore_mr(sr, sr, fr),       # 가격 스프레드 z
            'R3 펀딩MR': zscore_mr(fr, sr, fr),       # 카리 z
        }
        for rn, tr in runs.items():
            s = stats(tr)
            if s:
                print('  %-17s %-12s %3d %5d%% %+6.1f %+6.1f' % (nm, rn, s[0], s[1], s[2], s[3]))
            else:
                print('  %-17s %-12s  (거래<4)' % (nm, rn))
        print()


if __name__ == '__main__':
    main()
