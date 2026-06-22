# -*- coding: utf-8 -*-
"""
SKHX·SAMSUNG·DRAM·KR200 의 1시간 단위 펀딩 히스토리 → Excel.
시간당 세틀 금리(%) + 연율화(%) 둘 다. 최근까지.
실행: python backtest/FSSC/funding_export.py
"""
import sys
import os

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from governance.engine.prices import fetch_funding_history, fetch_candles

ASSETS = {'SKHX': 'xyz:SKHX', 'SAMSUNG': 'xyz:SMSN', 'DRAM': 'xyz:DRAM', 'KR200': 'xyz:KR200'}
DAYS = 200
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '한국주식_펀딩히스토리_1h.xlsx')


def main():
    per, settled, annual, price = {}, {}, {}, {}
    for name, sym in ASSETS.items():
        f = fetch_funding_history(sym, days=DAYS)   # 시간당 fundingRate (fraction)
        c = fetch_candles(sym, days=DAYS, interval='1h')  # 시간당 종가
        if f is None or not len(f):
            print(f'  {name}: 펀딩 데이터 없음'); continue
        fr = f['fundingRate']
        fr.index = fr.index.tz_localize(None).floor('h')   # 시각 정시 정렬
        s = (fr * 100).round(6)              # 시간당 세틀 금리(%) — 실제 지급요율
        a = (fr * 24 * 365 * 100).round(2)   # 연율화(%) = ×24×365
        df = pd.DataFrame({'시간당 세틀(%)': s, '연율화(%)': a})
        if c is not None and len(c):
            px = c['close'].copy(); px.index = px.index.tz_localize(None).floor('h')
            px = px[~px.index.duplicated()]
            df.insert(0, '가격', px.reindex(df.index).round(4))   # 가격을 맨 앞에
            price[name] = px
        df.index.name = 'time (UTC)'
        per[name] = df; settled[name] = s; annual[name] = a
        pxnote = f'최근가 {df["가격"].iloc[-1]}' if '가격' in df else '가격없음'
        print(f'  {name:8} {len(df)}시간 | {df.index.min()} ~ {df.index.max()} | '
              f'연율 {a.iloc[-1]:+.0f}% · {pxnote}')

    with pd.ExcelWriter(OUT, engine='openpyxl') as w:
        pd.DataFrame(price).to_excel(w, sheet_name='가격_비교')
        pd.DataFrame(annual).to_excel(w, sheet_name='연율화_비교(%)')
        pd.DataFrame(settled).to_excel(w, sheet_name='시간당세틀_비교(%)')
        for name, df in per.items():
            df.to_excel(w, sheet_name=name)   # 자산별: 가격+세틀+연율

    print('\n저장:', OUT)


if __name__ == '__main__':
    main()
