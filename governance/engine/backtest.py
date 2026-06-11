"""백테스트 엔진 (target + 적응형 alpha)."""

import numpy as np
import pandas as pd

from .profiles import COINS, FUND_PROFILES, REBALANCE_FEE
from .alpha import adaptive_alpha
from .voting import simulate_votes, votes_to_target, apply_ema

LOOKBACK = 14  # 모멘텀 기준 과거일수


def run_backtest(scenario_name, vote_generator, returns_df, profile,
                 initial_tvl=100_000, rebalance_every=7, coins=None,
                 deposits=(500, 300, 200)):
    """
    투표 시나리오를 과거 수익률에 적용해 펀드 자기자본 추이를 시뮬레이션.

    Args:
        scenario_name: 라벨용 문자열.
        vote_generator: (day_idx, participants, past, future) → participants.
        returns_df: 일간 수익률 DataFrame (코인별 컬럼).
        profile: FUND_PROFILES dict 또는 프로파일 dict.
        initial_tvl: 초기 자본.
        rebalance_every: 리밸런싱(투표) 주기, 일.
        coins: 대상 코인.
        deposits: 참여자 예치금 (가중치 결정).

    Returns:
        pd.DataFrame [equity, w_<coin>..., return, cum_return, drawdown, liquidated].
    """
    coins = coins or COINS
    if isinstance(profile, str):
        profile = FUND_PROFILES[profile]

    period = rebalance_every
    alpha = adaptive_alpha(period, profile['T_CONVERGE'])
    lev = profile['FUND_LEVERAGE']
    cap = profile['MAX_WEIGHT']

    participants = [{'name': chr(65 + i), 'deposit': d, 'votes': {}}
                    for i, d in enumerate(deposits)]

    equity = initial_tvl
    weights = {c: 100.0 / len(coins) for c in coins}  # 초기 균등 롱
    asset_pnl = {c: 0.0 for c in coins}               # 코인별 누적 손익($)
    history = []
    liquidated = False

    for day_idx, date in enumerate(returns_df.index):
        # 리밸런싱
        if day_idx % period == 0 and day_idx > 0:
            past = returns_df.iloc[max(0, day_idx - LOOKBACK):day_idx]
            future = returns_df.iloc[day_idx:day_idx + period]
            participants = vote_generator(day_idx, participants, past, future)
            target = votes_to_target(simulate_votes(participants, coins), coins)
            if target is not None:
                new_w = apply_ema(weights, target, alpha, cap, coins)
                turnover = sum(abs(new_w[c] - weights[c]) for c in coins) / 100
                equity -= turnover * equity * lev * REBALANCE_FEE
                weights = new_w

        # 일간 PnL (코인별로 분리 적립 → 리밸런싱 구간별 합산 정합)
        day_total = 0.0
        for c in coins:
            pnl = (weights[c] / 100) * equity * lev * returns_df.loc[date, c]
            asset_pnl[c] += pnl
            day_total += pnl
        equity += day_total

        if equity < initial_tvl * 0.1 and not liquidated:
            liquidated = True

        row = {'equity': max(equity, 0)}
        row.update({f'w_{c}': weights[c] for c in coins})
        row.update({f'pnl_{c}': asset_pnl[c] for c in coins})
        history.append(row)

    df = pd.DataFrame(history, index=returns_df.index)
    df['return'] = df['equity'].pct_change().fillna(0)
    df['cum_return'] = (df['equity'] / initial_tvl - 1) * 100
    df['drawdown'] = (df['equity'] / df['equity'].cummax() - 1) * 100
    df['scenario'] = scenario_name
    df['liquidated'] = liquidated
    # 코인별 누적 기여도(%) = 코인 누적손익 / 초기자본
    df.attrs['asset_contribution'] = {
        c: round(asset_pnl[c] / initial_tvl * 100, 2) for c in coins
    }
    return df


def calc_metrics(df, days_per_year=365):
    """누적/연환산 성과 지표."""
    r = df['return']
    n = len(df)
    ann_ret = df['cum_return'].iloc[-1] * days_per_year / n if n else 0
    ann_vol = r.std() * np.sqrt(days_per_year) * 100
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    max_dd = df['drawdown'].min()
    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0
    win_rate = (r > 0).mean() * 100
    return {
        'cum_return': round(df['cum_return'].iloc[-1], 1),
        'ann_return': round(ann_ret, 1),
        'ann_vol': round(ann_vol, 1),
        'sharpe': round(sharpe, 2),
        'max_drawdown': round(max_dd, 1),
        'calmar': round(calmar, 2),
        'win_rate': round(win_rate, 1),
        'liquidated': bool(df['liquidated'].iloc[-1]),
    }
