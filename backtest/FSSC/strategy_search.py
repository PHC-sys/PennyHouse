# -*- coding: utf-8 -*-
"""
FSSC 전략 탐색 (일별) — 4종목(SKHX,SMSN,DRAM,KR200)만.

발견자 규칙(핵심: 펀딩 카리 ⟷ MTM 평가손):
  진입: 당일 |카리(연환산)| 충분히 큼  AND  그날(전일대비) 카리방향 포지션의 MTM 음수
        (= 고펀딩 + 저평가 동시) → 카리+ 방향으로 진입
  청산: 펀딩 부호 역전 (held 방향 카리가 음수로)
  누적: 진입 다음날 수익률부터 청산일까지 [MTM + 카리] 누적 = 트레이드 손익
  (반대도 대칭: 큰 음수 카리 + MTM 양수)

여러 '구조'(롱/숏 조합) × MTM딥 필터 on/off × 진입임계 를 돌려 승률·총수익 비교.
일별 직접 계산(빠름). 최고 후보는 추후 엔진(수수료·시간당)으로 검증.
실행: python backtest/FSSC/strategy_search.py
"""
import sys
import os
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine.prices import fetch_candles, fetch_funding_history

A = {'SKHX': 'xyz:SKHX', 'SMSN': 'xyz:SMSN', 'DRAM': 'xyz:DRAM', 'KR200': 'xyz:KR200'}
DAYS = 110

# 구조: 기준 가중(롱+/숏−, 노셔널 1:1). 카리 부호로 전체 방향은 동적 플립됨.
STRUCTURES = {
    'chips/DRAM':   {'SKHX': -0.5, 'SMSN': -0.5, 'DRAM': 1.0},
    'chips/KR200':  {'SKHX': -0.5, 'SMSN': -0.5, 'KR200': 1.0},
    'DRAM/KR200':   {'DRAM': 1.0, 'KR200': -1.0},
    'SKHX/DRAM':    {'SKHX': 1.0, 'DRAM': -1.0},
    'SMSN/DRAM':    {'SMSN': 1.0, 'DRAM': -1.0},
    'chips/DRAM+KR': {'SKHX': -0.5, 'SMSN': -0.5, 'DRAM': 0.5, 'KR200': 0.5},
}


def load():
    R, Fd = {}, {}
    for nm, sym in A.items():
        c = fetch_candles(sym, days=DAYS + 5, interval='1d')
        if c is not None:
            s = c['close'].copy(); s.index = s.index.tz_localize(None)
            R[nm] = s.pct_change()
        f = fetch_funding_history(sym, days=DAYS + 5)
        if f is not None:
            d = f['fundingRate'].resample('1D').sum(); d.index = d.index.tz_localize(None)
            Fd[nm] = d            # 일별 펀딩(그날 시간당 합 = 일 지급률)
    return pd.DataFrame(R).dropna(), pd.DataFrame(Fd)


def backtest(struct, R, Fd, entry_ann, use_dip):
    """발견자 규칙 → 트레이드 리스트. entry_ann: |카리연환산%| 진입임계."""
    legs = list(struct)
    idx = R.index.intersection(Fd.index)
    R, Fd = R.loc[idx], Fd.loc[idx]
    # 기준 카리(연%)·기준 수익률(일)
    carry = -sum(struct[a] * Fd[a] for a in legs) * 365 * 100   # held=base일 때 일 카리의 연환산
    ret = sum(struct[a] * R[a] for a in legs)                   # held=base일 때 그날 MTM
    trades = []
    held = 0   # 0 flat, ±1 방향
    entry_i = None
    days = list(idx)
    for i in range(1, len(days)):
        c, r = carry.iloc[i], ret.iloc[i]
        if np.isnan(c) or np.isnan(r):
            continue
        d = 1 if c >= 0 else -1            # 카리+ 방향
        cpos = abs(c)                       # 카리+ 방향의 카리(연%)
        rpos = d * r                        # 카리+ 방향의 그날 MTM
        if held == 0:
            cond = cpos > entry_ann and (rpos < 0 if use_dip else True)
            if cond:
                held, entry_i, entry_dir = d, i, d
        else:
            # 펀딩 역전(held 방향 카리 음수) → 청산
            if (held == 1 and c < 0) or (held == -1 and c > 0):
                # 누적: 진입 다음날~청산일 [MTM+카리]
                pl = 0.0
                for j in range(entry_i + 1, i + 1):
                    pl += held * (ret.iloc[j] + (-sum(struct[a] * Fd[a].iloc[j] for a in legs)))
                trades.append(pl)
                held = 0
    return trades


def main():
    R, Fd = load()
    rows = []
    for use_dip in (True, False):
        for entry_ann in (30, 60):
            for nm, st in STRUCTURES.items():
                tr = backtest(st, R, Fd, entry_ann, use_dip)
                if not tr:
                    continue
                tr = np.array(tr)
                wins = (tr > 0).sum()
                rows.append({
                    'struct': nm, 'dip': 'Y' if use_dip else 'N', 'entry%': entry_ann,
                    'n': len(tr), 'win%': round(wins / len(tr) * 100),
                    'total%': round(tr.sum() * 100, 1), 'avg%': round(tr.mean() * 100, 2),
                    'best%': round(tr.max() * 100, 1), 'worst%': round(tr.min() * 100, 1),
                })
    df = pd.DataFrame(rows).sort_values(['win%', 'total%'], ascending=False)
    print(f'\n[FSSC 전략 탐색] {DAYS}일 일별 · 1x(무레버) · 수수료 미반영(직접계산)')
    print('  진입: |카리연%|>임계 + (dip=Y면 MTM음수) / 청산: 펀딩역전 / 누적: 진입익일~청산')
    with pd.option_context('display.width', 200, 'display.max_rows', 100):
        print(df.to_string(index=False))
    print('\n  ※ 승률만 보지 말 것 — n 작으면 노이즈, worst%(꼬리손실)·total% 같이 볼 것.')


if __name__ == '__main__':
    main()
