# -*- coding: utf-8 -*-
"""
FSSC 동적 헷지 테스트 — 롤링 다변량 회귀로 매일 헷지비율 갱신.

가설(발견자): 구성종목 파악 + 상관계수 비중 + 동적헷지 → 방향성 제거 → 카리 수확.
테스트: DRAM ~ β1·SKHX + β2·SMSN 롤링 회귀(매일) → 포지션 Long DRAM / Short β1 SKHX
/ Short β2 SMSN (최소분산 헷지). 방향성 뺀 뒤 잔여 손익을 [카리]/[잔여가격]으로 분해.

핵심 질문: 타이트 헷지 후 잔여 카리가 비용(일별 재헷지 수수료)을 이기고 net + 인가?
실행: python backtest/FSSC/dynamic_hedge.py
"""
import sys
import os
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine import run_simulation, fetch_universe
from governance.engine.prices import fetch_candles, fetch_funding_history

DRAM, CHIPS = 'xyz:DRAM', ['xyz:SKHX', 'xyz:SMSN']
DAYS = 100
WINDOW = 20         # 롤링 회귀 창(일)
LEVERAGE = 3
FEES = {'taker': 0.00045, 'maker': 0.00015, 'p_maker': 0.5}


def _build(R, F, days, start, carry_dir):
    """롤링 헷지 비중 스케줄. carry_dir=True면 펀딩부호로 방향 플립(카리+ 쪽)."""
    positions, r2s, flips = [], [], 0
    prev_dir = None
    for i in range(WINDOW, len(days)):
        ts = days[i]
        if ts.timestamp() < start:
            continue
        X = R[CHIPS].iloc[i - WINDOW:i].values
        y = R[DRAM].iloc[i - WINDOW:i].values
        A = np.column_stack([np.ones(len(X)), X])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        b1, b2 = float(coef[1]), float(coef[2])
        yhat = A @ coef
        ss_res, ss_tot = ((y - yhat) ** 2).sum(), ((y - y.mean()) ** 2).sum()
        r2s.append(1 - ss_res / ss_tot if ss_tot > 0 else 0)
        # 기준(Long DRAM) 헷지
        w0 = {DRAM: 100.0, CHIPS[0]: -100 * b1, CHIPS[1]: -100 * b2}
        d = 1
        if carry_dir and ts in F.index:
            f = F.loc[ts]
            # 기준 포지션의 펀딩손익 부호 = −Σ w·f. 음수(역카리)면 방향 플립.
            base = -(w0[DRAM] * f.get(DRAM, 0) + w0[CHIPS[0]] * f.get(CHIPS[0], 0)
                     + w0[CHIPS[1]] * f.get(CHIPS[1], 0))
            d = 1 if base >= 0 else -1
        if prev_dir is not None and d != prev_dir:
            flips += 1
        prev_dir = d
        positions.append({'t': int(ts.timestamp()),
                          'weights': {k: round(d * v, 2) for k, v in w0.items()},
                          'leverage': LEVERAGE})
    return positions, np.mean(r2s) if r2s else 0, flips


def _report(label, r, r2, flips):
    if not r:
        print(f'  {label}: 시뮬 실패'); return
    t = r['totals']
    cf = abs(t['funding']) / abs(t['price']) if t['price'] else float('inf')
    print(f'  [{label}]  잔여R² {r2:.2f} | 방향전환 {flips}회')
    print(f'     총 {t["ret_pct"]:+.2f}% | MDD {r["mdd_pct"]:.2f}% | '
          f'카리 {t["funding"]/1000:+.2f}% / 잔여가격 {t["price"]/1000:+.2f}% / 수수료 {t["fees"]/1000:+.2f}%'
          f' | 카리÷|가격| {cf:.2f}')


def main():
    reg = {a['symbol']: a for a in fetch_universe()}
    assets = [DRAM] + CHIPS
    now = int(time.time())
    start = now - DAYS * 86400

    closes = {}
    for a in assets:
        c = fetch_candles(a, days=DAYS + WINDOW + 5, interval='1d')
        if c is not None:
            closes[a] = c['close']
    P = pd.DataFrame(closes).sort_index(); P.index = P.index.tz_localize(None)
    R = P.pct_change().dropna()

    fr = {}
    for a in assets:
        f = fetch_funding_history(a, days=DAYS + WINDOW + 5)
        if f is not None:
            fr[a] = f['fundingRate']
    F = pd.DataFrame(fr).resample('1D').mean(); F.index = F.index.tz_localize(None)

    days = R.index
    print(f'\n[동적 헷지 테스트] {DAYS}일 · {LEVERAGE}x · 롤링{WINDOW}일 재헷지 · 일별')
    for carry_dir, lbl in [(False, '고정방향(Long DRAM)'), (True, '카리방향 플립(동적헷지+부호추종)')]:
        pos, r2, flips = _build(R, F, days, start, carry_dir)
        if not pos:
            continue
        r = run_simulation(assets, pos, pos[0]['t'], now, reg=reg, fees=FEES)
        _report(lbl, r, r2, flips)


if __name__ == '__main__':
    main()
