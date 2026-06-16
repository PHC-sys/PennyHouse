# -*- coding: utf-8 -*-
"""
FSSC 페어 백테스트 데모 — 헷지 방식별 손익 분해 비교.

한 페어를 (1) naive 1:1  (2) 베타가중 헷지  (3) 커스텀 비중 으로 돌려
[가격]/[펀딩]/[수수료]를 분해하고, "헷지를 조이면 캐리가 지배적이 되는가?"를 본다.
핵심 진단: 베타가중 시 |가격손익| 대비 |펀딩손익| 비율이 커지면 = 진짜 캐리 전략.

실행: python backtest/FSSC/run_pair.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine import run_simulation, hedge_beta, beta_weights, fetch_universe

PAIRS = {
    'pair1 칩 vs DRAM ETF': {'long': ['xyz:SKHX', 'xyz:SMSN'], 'short': ['xyz:DRAM']},
}
DAYS = 7
LEVERAGE = 3
# 커스텀 비중 예시(직접 조절) — None이면 건너뜀
CUSTOM = {'xyz:SKHX': 35, 'xyz:SMSN': 35, 'xyz:DRAM': -130}


def _naive(long, short):
    w = {a: round(100.0 / len(long), 4) for a in long}
    w.update({a: round(-100.0 / len(short), 4) for a in short})
    return w


def _run(label, assets, weights, start, now, reg, fees):
    r = run_simulation(assets, [{'t': start, 'weights': weights, 'leverage': LEVERAGE}],
                       start, now, reg=reg, fees=fees)
    if not r:
        print(f'  {label}: 데이터 부족'); return
    t = r['totals']
    ratio = abs(t['funding']) / abs(t['price']) if t['price'] else float('inf')
    print('  %-16s 총 %+8.0f (%+.2f%%) | MDD %6.2f%% | 가격 %+8.0f / 펀딩 %+7.0f / 수수료 %+5.0f | 펀딩÷|가격| %.2f'
          % (label, t['net'], t['ret_pct'], r['mdd_pct'], t['price'], t['funding'], t['fees'], ratio))


def main():
    reg = {a['symbol']: a for a in fetch_universe()}
    now = int(time.time())
    start = now - DAYS * 86400
    fees = {'taker': 0.00045, 'maker': 0.00015, 'p_maker': 0.5}

    for name, p in PAIRS.items():
        L, S = p['long'], p['short']
        assets = L + S
        h = hedge_beta(L, S, start, now)
        print(f'\n[{name}]  최근 {DAYS}일 · {LEVERAGE}x')
        if h:
            print('  헷지 회귀: β=%.3f  R²=%.3f  corr=%.3f  (vol 롱 %.4f / 숏 %.4f)'
                  % (h['beta'], h['r2'], h['corr'], h['vol_long'], h['vol_short']))
        print('  ─ "펀딩÷|가격|"이 클수록 캐리 지배(헷지 잘 됨) ─')
        _run('naive 1:1', assets, _naive(L, S), start, now, reg, fees)
        if h:
            bw = beta_weights(L, S, h['beta'])
            _run(f'베타가중 β={h["beta"]}', assets, bw, start, now, reg, fees)
        if CUSTOM:
            _run('커스텀', assets, CUSTOM, start, now, reg, fees)

        # ★ 기간 스윕 — 캐리는 시간 비례 누적, 방향성은 평균회귀 → 비율이 오르나?
        print('  ── 기간 스윕 (베타가중, 캐리 지배도 추세) ──')
        for d in (7, 14, 30, 60, 90):
            s = now - d * 86400
            hh = hedge_beta(L, S, s, now)
            if not hh:
                continue
            r = run_simulation(assets, [{'t': s, 'weights': beta_weights(L, S, hh['beta']),
                                         'leverage': LEVERAGE}], s, now, reg=reg, fees=fees)
            if not r:
                continue
            t = r['totals']
            ratio = abs(t['funding']) / abs(t['price']) if t['price'] else float('inf')
            print('    %3d일 (β=%.2f R²=%.2f): 펀딩 %+7.0f / 가격 %+8.0f → 펀딩÷|가격| %.2f | net %+.0f'
                  % (d, hh['beta'], hh['r2'], t['funding'], t['price'], ratio, t['net']))


if __name__ == '__main__':
    main()
