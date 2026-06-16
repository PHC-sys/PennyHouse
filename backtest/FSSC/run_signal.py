# -*- coding: utf-8 -*-
"""
FSSC 신호 백테스트 — 펀딩 괴리 진입 → 컨버전스(역캐리+베이시스 MTM) 실현 → 정리 → 반복.

전략(발견자 의도): 오래 들고 캐리 누적이 아님. 펀딩 스프레드가 벌어지면 진입(고펀딩
레그 숏/저펀딩 레그 롱, 베타가중), 스프레드가 수렴하면(=베이시스 MTM 실현) 정리. 반복.

신호: spread = fundingA(롱바스켓) − fundingB(숏바스켓), 연환산 %.
  spread > +진입  → A 숏 / B 롱  (A가 과프리미엄 → 수렴 베팅 + 캐리)
  spread < −진입  → A 롱 / B 숏
청산: |spread| < 청산(수렴) 또는 max_hold 또는 stop. 그 후 플랫, 다음 신호 대기.

엔진(engine.run_simulation)으로 평가 → 거래별/총 손익·MDD·승률.
실행: python backtest/FSSC/run_signal.py
"""
import sys
import os
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine import run_simulation, hedge_beta, beta_weights, fetch_universe
from governance.engine.prices import fetch_funding_history

# ── 페어 & 파라미터 ───────────────────────────────────────────────
LONG, SHORT = ['xyz:SKHX', 'xyz:SMSN'], ['xyz:DRAM']
DAYS = 120
LEVERAGE = 3
ENTRY = 60.0      # 진입: |스프레드| 연환산 % 초과
EXIT = 15.0       # 청산: |스프레드| 미만 (수렴, 히스테리시스)
MAX_HOLD = 10     # 최대 보유일
FEES = {'taker': 0.00045, 'maker': 0.00015, 'p_maker': 0.5}


def _funding_daily(assets, start, end):
    """자산별 일간 연환산 펀딩(%) 패널."""
    fr = {}
    for a in assets:
        f = fetch_funding_history(a, days=DAYS + 5)
        if f is not None and len(f):
            fr[a] = f['fundingRate']
    if not fr:
        return None
    df = pd.DataFrame(fr).resample('1D').mean() * 24 * 365 * 100
    idx = pd.date_range(pd.to_datetime(start, unit='s', utc=True).floor('D'),
                        pd.to_datetime(end, unit='s', utc=True).floor('D'), freq='D')
    return df.reindex(idx).ffill()


def main():
    reg = {a['symbol']: a for a in fetch_universe()}
    now = int(time.time())
    start = now - DAYS * 86400
    assets = LONG + SHORT

    fd = _funding_daily(assets, start, now)
    if fd is None:
        print('펀딩 데이터 없음'); return
    spread = fd[LONG].mean(axis=1) - fd[SHORT].mean(axis=1)

    # 진입/청산 규칙 → 포지션 스케줄 생성
    positions, trades = [], []
    state = 0          # -1 숏A, +1 롱A, 0 플랫
    entry_t = None
    days = list(spread.index)
    for i, ts in enumerate(days):
        s = spread.loc[ts]
        if np.isnan(s):
            continue
        tsec = int(ts.timestamp())
        if state == 0:
            if abs(s) > ENTRY:
                # 스프레드>0: A(롱바스켓) 과프리미엄 → A 숏/B 롱 (A에 거는 부호 = −1)
                direction = -1 if s > 0 else +1
                beta = (hedge_beta(LONG, SHORT, tsec - 14 * 86400, tsec) or {}).get('beta', 1.0)
                bw = beta_weights(LONG, SHORT, beta)   # A+, B− 기준 절대비중
                w = {a: round(direction * abs(bw[a]), 4) for a in LONG}
                w.update({a: round(-direction * abs(bw[a]), 4) for a in SHORT})
                positions.append({'t': tsec, 'weights': w, 'leverage': LEVERAGE})
                state, entry_t, entry_i, entry_spread = direction, tsec, i, s
        else:
            held = i - entry_i
            converged = abs(s) < EXIT
            flipped = (state == -1 and s < 0) or (state == 1 and s > 0)
            if converged or flipped or held >= MAX_HOLD:
                w = {a: 0.0 for a in assets}
                positions.append({'t': tsec, 'weights': w, 'leverage': LEVERAGE})
                trades.append((entry_t, tsec, entry_spread, s, held))
                state, entry_t = 0, None

    if not positions:
        print('신호 없음 (진입 임계 미달)'); return

    r = run_simulation(assets, positions, start, now, reg=reg, fees=FEES)
    if not r:
        print('시뮬 실패'); return

    # 거래별 손익 (equity 경계)
    eq = pd.Series({p['t']: None for p in []})
    navmap = {p['t']: p['value'] for p in r['nav']}
    nav_ts = sorted(navmap)

    def eq_at(tsec):
        import bisect
        j = bisect.bisect_right(nav_ts, tsec) - 1
        return navmap[nav_ts[max(j, 0)]]
    wins, pls = 0, []
    for (et, xt, es, xs, held) in trades:
        pl = eq_at(xt) / eq_at(et) - 1
        pls.append(pl)
        if pl > 0:
            wins += 1

    t = r['totals']
    in_market = sum(h for *_, h in trades)
    print(f'\n[FSSC 신호 백테스트] {DAYS}일 · {LEVERAGE}x · 진입>{ENTRY}% 청산<{EXIT}% maxhold{MAX_HOLD}d')
    print(f'  헷지: Long {LONG} / Short {SHORT}')
    print(f'  거래 {len(trades)}회 | 승률 {wins}/{len(trades)} = {wins/max(len(trades),1)*100:.0f}%'
          f' | 평균 보유 {np.mean([h for *_,h in trades]):.1f}일 | 시장노출 {in_market}/{DAYS}일')
    print(f'  총수익 {t["net"]:+.0f} ({t["ret_pct"]:+.2f}%) | MDD {r["mdd_pct"]:.2f}%')
    print(f'  분해: 가격 {t["price"]:+.0f} / 펀딩 {t["funding"]:+.0f} / 수수료 {t["fees"]:+.0f}')
    if pls:
        print(f'  트레이드별: 평균 {np.mean(pls)*100:+.2f}% | 최고 {max(pls)*100:+.1f}% | 최악 {min(pls)*100:+.1f}%')


if __name__ == '__main__':
    main()
