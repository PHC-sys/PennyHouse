# -*- coding: utf-8 -*-
"""
FSSC 페어 백테스트 데모 — 시뮬레이터 엔진(engine.simulate)으로 손익 분해.

한 페어를 정방향/플립 양쪽으로 돌려 [가격]/[펀딩]/[수수료]를 분해해서,
"어느 방향이 +였나, 그게 캐리인가 가격(베이시스)인가"를 데이터로 본다.
※ naive 1:1 노셔널 헷지. 베타가중·플립규칙·생존(MDD)·용량은 다음 단계.

실행: python backtest/FSSC/run_pair.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine import run_simulation, fetch_universe

# 페어 정의: long 다리 / short 다리 (정방향)
PAIRS = {
    'pair1 칩 vs DRAM ETF': {'long': ['xyz:SKHX', 'xyz:SMSN'], 'short': ['xyz:DRAM']},
    # 'pair2 SKHX vs KR200': {'long': ['xyz:SKHX'], 'short': ['xyz:KR200']},  # KR200 죽은시장
}
DAYS = 7
LEVERAGE = 3


def _weights(long, short, flip=False):
    """노셔널 1:1 정규화 비중. flip=True면 롱/숏 반대."""
    L, S = (short, long) if flip else (long, short)
    w = {}
    for a in L:
        w[a] = round(100.0 / len(L), 4)
    for a in S:
        w[a] = round(-100.0 / len(S), 4)
    return w


def _fmt(r):
    t = r['totals']
    print('  총 %+.0f (%+.2f%%) | MDD %.2f%% | 가격 %+.0f / 펀딩 %+.0f / 수수료 %+.0f'
          % (t['net'], t['ret_pct'], r['mdd_pct'], t['price'], t['funding'], t['fees']))
    for a, v in r['by_asset'].items():
        print('     %-10s 가격 %+8.0f  펀딩 %+8.0f'
              % (a.split(':')[-1], v['price_pnl'], v['funding_pnl']))


def main():
    reg = {a['symbol']: a for a in fetch_universe()}
    now = int(time.time())
    start = now - DAYS * 86400
    fees = {'taker': 0.00045, 'maker': 0.00015, 'p_maker': 0.5}

    for name, p in PAIRS.items():
        assets = p['long'] + p['short']
        print(f'\n[{name}]  최근 {DAYS}일 · {LEVERAGE}x · naive 1:1 헷지')
        for flip, label in [(False, '정방향 (Long칩/Short ETF)'),
                            (True, '플립    (Short칩/Long ETF)')]:
            pos = [{'t': start, 'weights': _weights(p['long'], p['short'], flip),
                    'leverage': LEVERAGE}]
            r = run_simulation(assets, pos, start, now, reg=reg, fees=fees)
            if not r:
                print(f'  {label}: 데이터 부족'); continue
            print(f'  {label}')
            _fmt(r)


if __name__ == '__main__':
    main()
