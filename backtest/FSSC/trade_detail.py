# -*- coding: utf-8 -*-
"""
FSSC 트레이드 정밀 분석 — KR200/DRAM 구조의 모든 트레이드를 날짜별 분해.
진짜 반복 패턴인지(일관) vs 한두 아웃라이어인지 판정. 카리⟷MTM 기여 분리.
실행: python backtest/FSSC/trade_detail.py
"""
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy_search import load  # noqa

STRUCT = {'DRAM': 1.0, 'KR200': -1.0}   # 기준: Long DRAM / Short KR200 (카리부호로 동적 플립)
ENTRY = 30


def detail(struct, R, Fd, entry_ann, use_dip=True):
    legs = list(struct)
    idx = R.index.intersection(Fd.index)
    R, Fd = R.loc[idx], Fd.loc[idx]
    carry_ann = -sum(struct[a] * Fd[a] for a in legs) * 365 * 100
    ret = sum(struct[a] * R[a] for a in legs)
    fund_d = -sum(struct[a] * Fd[a] for a in legs)        # 일 카리(기준방향)
    days = list(idx)
    held, ei, ec = 0, None, None
    out = []
    for i in range(1, len(days)):
        c, r = carry_ann.iloc[i], ret.iloc[i]
        if np.isnan(c):
            continue
        d = 1 if c >= 0 else -1
        if held == 0:
            if abs(c) > entry_ann and (d * r < 0 if use_dip else True):
                held, ei, ec = d, i, c
        elif (held == 1 and c < 0) or (held == -1 and c > 0):
            mtm = sum(held * ret.iloc[j] for j in range(ei + 1, i + 1))
            car = sum(held * fund_d.iloc[j] for j in range(ei + 1, i + 1))
            out.append({
                'entry': days[ei].strftime('%Y-%m-%d'), 'exit': days[i].strftime('%Y-%m-%d'),
                'hold': i - ei, 'dir': 'Long DRAM/Short KR200' if held > 0 else 'Long KR200/Short DRAM',
                'entry_carry%': round(ec), 'MTM%': round(mtm * 100, 2),
                'carry%': round(car * 100, 2), 'total%': round((mtm + car) * 100, 2)})
            held = 0
    return out


def main():
    R, Fd = load()[0], load()[1]
    tr = detail(STRUCT, R, Fd, ENTRY)
    df = pd.DataFrame(tr)
    print(f'\n[KR200/DRAM 정밀 분석] 진입임계 {ENTRY}% · dip=Y · 1x · 수수료 미반영')
    with pd.option_context('display.width', 200):
        print(df.to_string(index=False))
    tot = df['total%'].values
    wins = (tot > 0).sum()
    print(f'\n  거래 {len(tot)} | 승 {wins} 패 {len(tot)-wins} = 승률 {wins/len(tot)*100:.0f}%')
    print(f'  총 {tot.sum():+.1f}% | 평균 {tot.mean():+.2f}% | 중앙값 {np.median(tot):+.2f}%')
    print(f'  카리 합 {df["carry%"].sum():+.1f}% | MTM 합 {df["MTM%"].sum():+.1f}%  (수익 출처)')
    # 아웃라이어 검정
    s = np.sort(tot)[::-1]
    print(f'  최고 트레이드 {s[0]:+.1f}% 제외 시 총 {tot.sum()-s[0]:+.1f}% (승률 {(np.delete(tot,np.argmax(tot))>0).mean()*100:.0f}%)')
    print(f'  상위 2개 제외 시 총 {tot.sum()-s[0]-s[1]:+.1f}%')
    print(f'  방향 분포: {df["dir"].value_counts().to_dict()}')


if __name__ == '__main__':
    main()
