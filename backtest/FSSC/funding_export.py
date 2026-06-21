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
from governance.engine.prices import fetch_funding_history

ASSETS = {'SKHX': 'xyz:SKHX', 'SAMSUNG': 'xyz:SMSN', 'DRAM': 'xyz:DRAM', 'KR200': 'xyz:KR200'}
DAYS = 200
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '한국주식_펀딩히스토리_1h.xlsx')


def main():
    per = {}      # name -> DataFrame[시간당세틀%, 연율화%]
    settled = {}  # 연율 비교용
    annual = {}
    for name, sym in ASSETS.items():
        f = fetch_funding_history(sym, days=DAYS)   # 시간당 fundingRate (fraction)
        if f is None or not len(f):
            print(f'  {name}: 데이터 없음'); continue
        fr = f['fundingRate']
        fr.index = fr.index.tz_localize(None)
        s = (fr * 100).round(6)              # 시간당 세틀 금리(%) — 실제 지급요율
        a = (fr * 24 * 365 * 100).round(2)   # 연율화(%) = ×24×365
        df = pd.DataFrame({'시간당 세틀(%)': s, '연율화(%)': a})
        df.index.name = 'time (UTC)'
        per[name] = df
        settled[name] = s
        annual[name] = a
        print(f'  {name:8} {len(df)}시간 | {df.index.min()} ~ {df.index.max()} | '
              f'최근 연율 {a.iloc[-1]:+.0f}%')

    with pd.ExcelWriter(OUT, engine='openpyxl') as w:
        # 비교용 통합 시트
        pd.DataFrame(annual).to_excel(w, sheet_name='연율화_비교(%)')
        pd.DataFrame(settled).to_excel(w, sheet_name='시간당세틀_비교(%)')
        # 자산별 (세틀+연율)
        for name, df in per.items():
            df.to_excel(w, sheet_name=name)

    print('\n저장:', OUT)


if __name__ == '__main__':
    main()
