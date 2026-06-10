# -*- coding: utf-8 -*-
"""governance.engine 모듈 검증 (assert)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from governance.engine import (
    VOLATILITY, COINS, FUND_PROFILES,
    adaptive_alpha, simulate_votes, votes_to_target,
    fetch_closes, make_generator, run_backtest, calc_metrics,
)


def test_adaptive_alpha():
    assert abs(adaptive_alpha(7, 7) - 0.9) < 1e-9
    assert abs(adaptive_alpha(1, 7) - (1 - 0.1 ** (1/7))) < 1e-12
    assert adaptive_alpha(7, 7) > adaptive_alpha(1, 7) > adaptive_alpha(0.25, 7)
    print("  [1] adaptive_alpha 수학 ✅")


def test_calendar_invariance():
    TARGET, START, T = -60.0, 25.0, 7
    aw = adaptive_alpha(7, T); cw = aw*TARGET + (1-aw)*START
    ad = adaptive_alpha(1, T); cd = START
    for _ in range(7): cd = ad*TARGET + (1-ad)*cd
    assert abs(cw - cd) < 3.0
    print(f"  [2] 달력 수렴 불변성 (주간 {cw:.1f}% ≈ 일간 {cd:.1f}%) ✅")


def test_votes_commonsense():
    ps = [{'deposit':6000,'votes':{'BTC':2,'ETH':0,'SOL':-1,'HYPE':1}},
          {'deposit':3000,'votes':{'BTC':1,'ETH':2,'SOL':0,'HYPE':-1}},
          {'deposit':1000,'votes':{'BTC':-2,'ETH':1,'SOL':2,'HYPE':0}}]
    tgt = votes_to_target(simulate_votes(ps))
    assert tgt['BTC'] > 0 and tgt['ETH'] > 0 and tgt['SOL'] < 0 and tgt['HYPE'] > 0
    assert abs(sum(abs(v) for v in tgt.values()) - 100) < 1e-6
    ps[0]['votes']['BTC'] = -2
    assert votes_to_target(simulate_votes(ps))['BTC'] < 0
    print("  [3] votes_to_target 상식+큰손우선+정규화 ✅")


def test_backtest_perfect_wins():
    closes, returns = fetch_closes(days=180)
    assert returns is not None and len(returns) > 50, "HL 데이터 수집 실패"
    bh = ((1 + returns.mean(axis=1)).cumprod().iloc[-1] - 1) * 100
    for pname in FUND_PROFILES:
        res = {}
        for s in ['momentum', 'random', 'perfect']:
            df = run_backtest(s, make_generator(s), returns, pname)
            res[s] = calc_metrics(df)['cum_return']
        assert res['perfect'] > res['momentum']
        assert res['perfect'] > res['random']
        assert res['perfect'] > bh
        print(f"  [4-{pname[:4]}] Perfect {res['perfect']:+.0f}% > 나머지·B&H({bh:+.0f}%) ✅")


def test_period_invariance():
    closes, returns = fetch_closes(days=180)
    bh = ((1 + returns.mean(axis=1)).cumprod().iloc[-1] - 1) * 100
    for period in [7, 3, 1]:
        df = run_backtest('perfect', make_generator('perfect'), returns,
                          'aggressive', rebalance_every=period)
        assert calc_metrics(df)['cum_return'] > bh
        print(f"  [5] 주기 {period}일 Perfect > B&H ✅")


if __name__ == '__main__':
    print("=" * 60)
    print("  governance.engine 모듈 검증")
    print("=" * 60)
    test_adaptive_alpha()
    test_calendar_invariance()
    test_votes_commonsense()
    test_backtest_perfect_wins()
    test_period_invariance()
    print("=" * 60)
    print("  전체 통과 — 모듈이 노트북과 동일하게 작동")
    print("=" * 60)
