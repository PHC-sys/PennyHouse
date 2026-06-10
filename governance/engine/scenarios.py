"""백테스트용 투표 시나리오 생성기."""

import numpy as np
from .profiles import COINS


def score_to_vote(x):
    """연속 신호 → 5단계 이산 투표(-2~+2)."""
    if x > 0.5:
        return 2
    if x > 0.1:
        return 1
    if x < -0.5:
        return -2
    if x < -0.1:
        return -1
    return 0


def gen_momentum(returns_window, participants, coins=None):
    """최근 수익률 방향으로 투표 (추세 추종)."""
    coins = coins or COINS
    for p in participants:
        for c in coins:
            ret = returns_window[c].sum() if c in returns_window else 0
            p['votes'][c] = score_to_vote(ret / 0.1)
    return participants


def gen_contrarian(returns_window, participants, coins=None):
    """최근 수익률 반대로 투표 (역추세)."""
    coins = coins or COINS
    for p in participants:
        for c in coins:
            ret = returns_window[c].sum() if c in returns_window else 0
            p['votes'][c] = score_to_vote(-ret / 0.1)
    return participants


def gen_random(participants, seed=None, coins=None):
    """완전 랜덤 투표."""
    coins = coins or COINS
    rng = np.random.default_rng(seed)
    for p in participants:
        for c in coins:
            p['votes'][c] = int(rng.choice([-2, -1, 0, 1, 2],
                                           p=[0.1, 0.2, 0.4, 0.2, 0.1]))
    return participants


def gen_perfect(returns_forward, participants, coins=None):
    """미래 수익률을 알고 투표 (이론적 상한선)."""
    coins = coins or COINS
    for p in participants:
        for c in coins:
            ret = returns_forward[c].sum() if c in returns_forward else 0
            p['votes'][c] = score_to_vote(ret / 0.1)
    return participants


def make_generator(scenario, coins=None):
    """
    시나리오명 → vote_generator(day_idx, participants, past, future) 콜백.
    """
    coins = coins or COINS

    def gen(day_idx, participants, past, future):
        if scenario == 'momentum':
            return gen_momentum(past, participants, coins)
        if scenario == 'contrarian':
            return gen_contrarian(past, participants, coins)
        if scenario == 'perfect':
            return gen_perfect(future, participants, coins)
        return gen_random(participants, seed=day_idx, coins=coins)

    return gen
