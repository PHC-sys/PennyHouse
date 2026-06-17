# -*- coding: utf-8 -*-
"""
4개 자산(SKHX, SAMSUNG, DRAM, KR200)의 펀딩비·가격 전체 시계열을 Excel로 덤프.
실행: python backtest/FSSC/export_xlsx.py  → FSSC_funding_price.xlsx
"""
import sys
import os

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine.prices import fetch_candles, fetch_funding_history

ASSETS = {'SKHX': 'xyz:SKHX', 'SAMSUNG': 'xyz:SMSN', 'DRAM': 'xyz:DRAM', 'KR200': 'xyz:KR200'}
DAYS = 120
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'FSSC_funding_price.xlsx')


def _naive(df):
    df = df.copy()
    df.index = df.index.tz_localize(None)   # Excel은 tz-aware datetime 못 씀
    df.index.name = 'time (UTC)'
    return df


def main():
    price_h, fund_h = {}, {}
    for name, sym in ASSETS.items():
        c = fetch_candles(sym, days=DAYS, interval='1h')
        if c is not None and len(c):
            price_h[name] = c['close']
        f = fetch_funding_history(sym, days=DAYS)
        if f is not None and len(f):
            fund_h[name] = f['fundingRate']

    P = pd.DataFrame(price_h).sort_index()
    Fraw = pd.DataFrame(fund_h).sort_index()
    Fann = Fraw * 24 * 365 * 100             # 연환산 %

    Pd = P.resample('1D').last()
    Fd = Fann.resample('1D').mean()
    daily = pd.concat({'Price': Pd, 'Funding_ann_%': Fd}, axis=1).round(4)
    # 일별 펀딩 스프레드(연%)
    if {'SKHX', 'SAMSUNG', 'DRAM', 'KR200'} <= set(Fd.columns):
        sp = pd.DataFrame({
            'chips_vs_DRAM': (Fd[['SKHX', 'SAMSUNG']].mean(axis=1) - Fd['DRAM']).round(1),
            'chips_vs_KR200': (Fd[['SKHX', 'SAMSUNG']].mean(axis=1) - Fd['KR200']).round(1),
        })
        daily[('Funding_spread', 'chips-DRAM')] = sp['chips_vs_DRAM']
        daily[('Funding_spread', 'chips-KR200')] = sp['chips_vs_KR200']

    with pd.ExcelWriter(OUT, engine='openpyxl') as w:
        _naive(daily).to_excel(w, sheet_name='Daily (일별)')
        _naive(Fann.round(3)).to_excel(w, sheet_name='Funding_ann% (시간당)')
        _naive(P.round(4)).to_excel(w, sheet_name='Price (시간당)')
        _naive(Fraw.round(8)).to_excel(w, sheet_name='Funding_raw (시간당)')

    print('저장:', OUT)
    print('가격 시간당 %d행, 펀딩 시간당 %d행' % (len(P), len(Fraw)))
    print('기간:', P.index.min(), '~', P.index.max())


if __name__ == '__main__':
    main()
