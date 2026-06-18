# -*- coding: utf-8 -*-
"""
FSSC 신호 전략 × 동적 베타헷지 비중 비교 (고정 달러뉴트럴 vs 롤링 베타).
신호(고펀딩+MTM딥 진입 / 펀딩역전 청산)는 동일, 비중 결정만 바꿔 비교.
실행: python backtest/FSSC/beta_signal.py
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy_search import load  # noqa

W = 20          # 롤링 회귀 창
ENTRY = 30
STRUCTS = {
    'DRAM/KR200':       (['DRAM'], ['KR200']),
    'KR200/SKHX+DRAM':  (['KR200'], ['SKHX', 'DRAM']),
    'chips/DRAM':       (['SKHX', 'SMSN'], ['DRAM']),
    'chips/KR200':      (['SKHX', 'SMSN'], ['KR200']),
}


def w_naive(long, short):
    w = {a: 1.0 / len(long) for a in long}
    w.update({a: -1.0 / len(short) for a in short})
    return w


def w_beta(long, short, Rwin):
    """롱바스켓 ~ 숏자산들 회귀 → 숏 비중 = −β (최소분산 헷지). 롱 +1 정규화."""
    Xs = Rwin[short].values
    yl = Rwin[long].mean(axis=1).values
    A = np.column_stack([np.ones(len(Xs)), Xs])
    coef, *_ = np.linalg.lstsq(A, yl, rcond=None)
    w = {a: 1.0 / len(long) for a in long}
    for a, b in zip(short, coef[1:]):
        w[a] = -float(b)
    return w


def run(long, short, R, Fd, mode):
    assets = long + short
    idx = R.index.intersection(Fd.index)
    R, Fd = R.loc[idx], Fd.loc[idx]
    days = list(idx)
    trades, held, ei = [], 0, None
    for i in range(1, len(days)):
        if mode == 'beta' and i < W:
            continue
        w = w_naive(long, short) if mode == 'naive' else w_beta(long, short, R.iloc[i - W:i])
        carry = -sum(w[a] * Fd[a].iloc[i] for a in assets) * 365 * 100
        ret = sum(w[a] * R[a].iloc[i] for a in assets)
        if np.isnan(carry) or np.isnan(ret):
            continue
        d = 1 if carry >= 0 else -1
        if held == 0:
            if abs(carry) > ENTRY and d * ret < 0:
                held, ei = d, i
        elif (held == 1 and carry < 0) or (held == -1 and carry > 0):
            pl = 0.0
            for j in range(ei + 1, i + 1):
                wj = w_naive(long, short) if mode == 'naive' else w_beta(long, short, R.iloc[j - W:j])
                pl += held * (sum(wj[a] * R[a].iloc[j] for a in assets)
                              - sum(wj[a] * Fd[a].iloc[j] for a in assets))
            trades.append(pl)
            held = 0
    return np.array(trades)


def main():
    R, Fd = load()[0], load()[1]
    print(f'\n[신호 전략 × 비중방식] 진입{ENTRY}% · dip=Y · 롤링{W}일 · 1x · 수수료 미반영')
    print('  %-18s %-7s %3s %6s %8s %8s' % ('구조', '비중', 'n', '승률%', '총%', '최악%'))
    for nm, (lo, sh) in STRUCTS.items():
        for mode in ('naive', 'beta'):
            tr = run(lo, sh, R, Fd, mode)
            if len(tr) == 0:
                print('  %-18s %-7s  (거래 없음)' % (nm, mode)); continue
            print('  %-18s %-7s %3d %5d%% %+7.1f %+7.1f'
                  % (nm, mode, len(tr), round((tr > 0).mean() * 100),
                     tr.sum() * 100, tr.min() * 100))


if __name__ == '__main__':
    main()
