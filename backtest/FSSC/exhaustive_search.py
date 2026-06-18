# -*- coding: utf-8 -*-
"""
FSSC 전수 탐색 — 4종목 롱/숏/제외 모든 조합(헷지 구조) × 발견자 규칙.
실행: python backtest/FSSC/exhaustive_search.py
"""
import sys
import os
from itertools import product

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy_search import load, backtest, A  # noqa

ASSETS = list(A)


def all_structures():
    """롱·숏 둘 다 포함하는 달러뉴트럴 조합 (부호반전 중복 제거)."""
    seen, out = set(), {}
    for signs in product([-1, 0, 1], repeat=4):
        if not any(x > 0 for x in signs) or not any(x < 0 for x in signs):
            continue
        if tuple(-x for x in signs) in seen:
            continue
        seen.add(signs)
        longs = [a for a, x in zip(ASSETS, signs) if x > 0]
        shorts = [a for a, x in zip(ASSETS, signs) if x < 0]
        w = {a: 1.0 / len(longs) for a in longs}
        w.update({a: -1.0 / len(shorts) for a in shorts})
        out['+'.join(longs) + ' / ' + '+'.join(shorts)] = w
    return out


def main():
    R, Fd = load()[0], load()[1]
    structs = all_structures()
    rows = []
    for nm, st in structs.items():
        for entry_ann in (30, 50):
            tr = backtest(st, R, Fd, entry_ann, use_dip=True)
            if len(tr) < 4:
                continue
            pls = np.array(tr)
            rows.append([nm, entry_ann, len(pls), round((pls > 0).mean() * 100),
                         round(pls.sum() * 100, 1), round(pls.mean() * 100, 2),
                         round(pls.min() * 100, 1)])
    df = pd.DataFrame(rows, columns=['구조(롱/숏)', '진입%', 'n', '승률%', '총%', '평균%', '최악%'])
    df = df.sort_values(['승률%', '총%'], ascending=False).reset_index(drop=True)
    print(f'\n[전수 탐색] 헷지구조 {len(structs)}개 × 진입임계 2개 · dip=Y · 1x · 수수료 미반영')
    with pd.option_context('display.width', 200, 'display.max_rows', 200):
        print('── 상위 15 ──'); print(df.head(15).to_string(index=False))
        print('\n── (SKHX+SMSN / DRAM) 위치 ──')
        print(df[df['구조(롱/숏)'].str.contains('SKHX') & df['구조(롱/숏)'].str.contains('SMSN')
                 & df['구조(롱/숏)'].str.contains('DRAM') & ~df['구조(롱/숏)'].str.contains('KR200')].to_string(index=False))
        print('\n── 하위 5 ──'); print(df.tail(5).to_string(index=False))
    print('\n※ 구조 %d개 × 2임계 = %d개 테스트. n 작아(5~12) 승률 상위는 일부 우연 포함.' % (len(structs), len(rows)))
    print('  로버스트 신호 = 두 임계 모두 상위 + n 충분 + 최악% 작음 인 것.')


if __name__ == '__main__':
    main()
