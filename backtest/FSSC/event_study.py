# -*- coding: utf-8 -*-
"""
FSSC 이벤트 스터디 — 펀딩 괴리 진입 시점마다, 진입일부터 3일간 펀딩 & MTM 추이.

요청 시나리오:
  · 페어1: SKHX, SAMSUNG(SMSN) vs DRAM
  · 페어2: SKHX, SAMSUNG(SMSN) vs KR200
  · 펀딩 스프레드 괴리가 클 때 진입(롱숏은 괴리 방향: 고펀딩 숏/저펀딩 롱)
  · 각 진입일부터 D+1/2/3 의 [펀딩 손익] [MTM(가격) 손익] [스프레드] 시계열

엔진(engine.run_simulation)으로 평가 — 펀딩은 매시간 적립(=캐리 반영).
실행: python backtest/FSSC/event_study.py
"""
import sys
import os
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine import run_simulation, hedge_beta, beta_weights, fetch_universe
from governance.engine.prices import fetch_funding_history

PAIRS = {
    '1) SKHX+SMSN vs DRAM': {'long': ['xyz:SKHX', 'xyz:SMSN'], 'short': ['xyz:DRAM']},
    '2) SKHX+SMSN vs KR200': {'long': ['xyz:SKHX', 'xyz:SMSN'], 'short': ['xyz:KR200']},
}
DAYS = 120          # 과거 조회 기간
ENTRY = 50.0        # 진입: |스프레드| 연환산 % 초과 (괴리)
HORIZON = 4         # 진입일부터 추적 일수 (D, D+1, D+2, D+3)
LEVERAGE = 3
INIT = 100000.0
FEES = {'taker': 0.00045, 'maker': 0.00015, 'p_maker': 0.5}


def _funding_daily(assets):
    fr = {}
    for a in assets:
        f = fetch_funding_history(a, days=DAYS + 5)
        if f is not None and len(f):
            fr[a] = f['fundingRate']
    if not fr:
        return None
    return (pd.DataFrame(fr).resample('1D').mean() * 24 * 365 * 100).dropna(how='all')


def _pct(v):
    return v / INIT * 100.0


def study(name, long, short):
    assets = long + short
    fd = _funding_daily(assets)
    if fd is None or any(a not in fd.columns for a in assets):
        print(f'\n[{name}] 펀딩 데이터 부족 (자산 누락) — 스킵'); return
    spread = (fd[long].mean(axis=1) - fd[short].mean(axis=1)).dropna()

    # 진입 이벤트 = |스프레드|가 임계 위로 새로 올라선 날 (신선한 괴리)
    events = []
    days = list(spread.index)
    for i in range(1, len(days)):
        s, sp = spread.iloc[i], spread.iloc[i - 1]
        if abs(s) > ENTRY and abs(sp) <= ENTRY:
            events.append(days[i])

    labels = ['D', 'D+1', 'D+2', 'D+3']    # 진입일부터 누적 (D=진입~+1일)
    print(f'\n[{name}]  진입임계 |spread|>{ENTRY}% · {LEVERAGE}x · 베타가중 · 진입 {len(events)}건')
    if not events:
        print('  (괴리 이벤트 없음 — 임계 낮추거나 데이터 확인)'); return
    print('  날짜        방향     진입sprd | ' +
          ' | '.join('%s 펀딩/MTM/계' % L for L in labels) + ' | spread경로')

    agg = {d: {'f': [], 'm': [], 't': []} for d in range(1, HORIZON + 1)}
    for t0 in events:
        s0 = spread.loc[t0]
        t0s = int(t0.timestamp())
        dir_a = -1 if s0 > 0 else +1                    # 고펀딩 A → 숏(-)
        beta = (hedge_beta(long, short, t0s - 14 * 86400, t0s) or {}).get('beta', 1.0)
        bw = beta_weights(long, short, beta)
        w = {a: round(dir_a * abs(bw[a]), 4) for a in long}
        w.update({a: round(-dir_a * abs(bw[a]), 4) for a in short})
        label = 'A숏 B롱' if dir_a < 0 else 'A롱 B숏'

        cells = []
        for d in range(1, HORIZON + 1):
            r = run_simulation(assets, [{'t': t0s, 'weights': w, 'leverage': LEVERAGE}],
                               t0s, t0s + d * 86400, reg=REG, fees=FEES)
            if not r:
                cells.append('   n/a        '); continue
            f, m, tot = _pct(r['totals']['funding']), _pct(r['totals']['price']), r['totals']['ret_pct']
            agg[d]['f'].append(f); agg[d]['m'].append(m); agg[d]['t'].append(tot)
            cells.append('%+5.2f/%+5.2f/%+5.2f' % (f, m, tot))
        sp_path = []
        fut = spread[spread.index > t0]
        for d in range(1, HORIZON + 1):
            sp_path.append('%+.0f' % fut.iloc[d - 1] if len(fut) >= d else '·')
        print('  %s  %-7s %+6.0f%% | %s | %s'
              % (t0.strftime('%Y-%m-%d'), label, s0, ' | '.join(cells), '/'.join(sp_path)))

    print('  ── 평균 (전 이벤트, 진입일부터 누적 %, MTM+면 수렴/MTM−면 추세) ──')
    for d in range(1, HORIZON + 1):
        if agg[d]['t']:
            print('    %-4s: 펀딩 %+.2f%% | MTM %+.2f%% | 계 %+.2f%%  (n=%d)'
                  % (labels[d - 1], np.mean(agg[d]['f']), np.mean(agg[d]['m']),
                     np.mean(agg[d]['t']), len(agg[d]['t'])))


REG = None


def main():
    global REG
    REG = {a['symbol']: a for a in fetch_universe()}
    for name, p in PAIRS.items():
        study(name, p['long'], p['short'])


if __name__ == '__main__':
    main()
