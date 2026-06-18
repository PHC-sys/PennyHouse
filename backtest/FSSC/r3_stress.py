# -*- coding: utf-8 -*-
"""
R3(베타헷지 상대 모멘텀) 스트레스 테스트 — +수익이 진짜 엣지인가 팻테일 운빨인가.
중앙값 / 아웃라이어 의존 / 수수료 후 / 분포 정직 해부.
실행: python backtest/FSSC/r3_stress.py
"""
import sys
import os
from itertools import combinations

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner import liquid_universe, load, _beta, TOP_N, CORR_MIN, W  # noqa
from multi_rule_scan import spread, Zrule  # noqa

# 대략 수수료: 진입/청산 + 일별 재헷지. 2다리 왕복 + 보유일 재헷지 근사.
FEE_PER_FILL = 0.0003   # 블렌디드(테이커0.045/메이커0.015, p_maker0.5)


def main():
    syms = [s for s, _ in liquid_universe(TOP_N)]
    R, Fd = load(syms)
    common = [s for s in syms if s in R.columns and s in Fd.columns and R[s].notna().sum() > 60]
    corr = R[common].corr()
    pairs = [(a, b) for a, b in combinations(common, 2) if corr.loc[a, b] >= CORR_MIN]

    trades = []
    for a, b in pairs:
        ret, fund = spread(a, b, R, Fd)
        trades += Zrule(ret, fund, 'MOM')
    trades = [t for t in trades if not np.isnan(t[0])]   # 데이터 갭 트레이드 제거

    pl = np.array([t[0] for t in trades])
    hold = np.array([t[3] for t in trades])
    n = len(pl)
    # 수수료: 진입+청산 4체결 + 보유일 재헷지(하루 2다리 조정 근사)
    fee = (4 + hold * 2) * FEE_PER_FILL
    pln = pl - fee

    print(f'\n[R3 상대모멘텀 스트레스] n={n} · 베타헷지 · 1x')
    print('── 분포 (수수료 전) ──')
    print(f'  승률 {(pl>0).mean()*100:.0f}% | 평균 {pl.mean()*100:+.2f}% | 중앙값 {np.median(pl)*100:+.2f}%'
          f' | std {pl.std()*100:.1f}%')
    print(f'  총 {pl.sum()*100:+.0f}% | 분위 10/25/50/75/90: '
          + '/'.join(f'{np.percentile(pl,q)*100:+.1f}' for q in (10, 25, 50, 75, 90)))
    print('── 아웃라이어 의존 (수수료 전) ──')
    s = np.sort(pl)[::-1]
    for k in (1, 3, 5, 10):
        print(f'  상위 {k:2d} 제외: 총 {(pl.sum()-s[:k].sum())*100:+.0f}%  '
              f'(상위{k}가 전체이익의 {s[:k][s[:k]>0].sum()/pl[pl>0].sum()*100:.0f}%)')
    print('── 수수료 후 ──')
    print(f'  평균 {pln.mean()*100:+.2f}% | 중앙값 {np.median(pln)*100:+.2f}% | '
          f'총 {pln.sum()*100:+.0f}% | 승률 {(pln>0).mean()*100:.0f}%')
    win, loss = pln[pln > 0], pln[pln < 0]
    pf = win.sum() / -loss.sum() if len(loss) else float('inf')
    print(f'  PF {pf:.2f} | 평균승 {win.mean()*100:+.2f}% 평균패 {loss.mean()*100:+.2f}%')
    # 비독립 보정: 같은 날 동시진입 많음 → 유효표본 << n. 거칠게 페어수로 down.
    print(f'  ※ 유효표본 << {n} (동시 트레이드 상관). t값 신뢰 말 것.')
    print('  판정: 중앙값>0 & 상위 몇개 빼도 +면 엣지 가능. 아니면 팻테일 운빨.')


if __name__ == '__main__':
    main()
