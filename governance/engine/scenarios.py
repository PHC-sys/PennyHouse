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


def gen_ma_cross(returns_window, participants, coins=None):
    """
    단기 vs 장기 평균수익률 교차 (이평선 골든/데드크로스 근사).
    최근 절반 평균 > 전체 평균 → 상승추세 → 롱.
    """
    coins = coins or COINS
    n = len(returns_window)
    half = max(1, n // 2)
    for p in participants:
        for c in coins:
            if c not in returns_window:
                p['votes'][c] = 0
                continue
            short = returns_window[c].iloc[-half:].mean()
            long = returns_window[c].mean()
            p['votes'][c] = score_to_vote((short - long) / 0.02)
    return participants


def gen_always_long(participants, coins=None):
    """항상 균등 풀 롱 (레버리지 효과 기준선)."""
    coins = coins or COINS
    for p in participants:
        for c in coins:
            p['votes'][c] = 2
    return participants


# 시나리오 메타 (프론트 표시용)
SCENARIO_META = {
    'momentum':   {'label': '모멘텀',      'desc': '최근 오른 코인 롱 (추세추종)'},
    'contrarian': {'label': '역추세',      'desc': '최근 오른 코인 숏'},
    'ma_cross':   {'label': '이평선 교차',  'desc': '단기>장기 평균이면 롱'},
    'random':     {'label': '랜덤',        'desc': '무작위 투표'},
    'always_long':{'label': '레버리지 롱',  'desc': '균등 풀 롱 (펀드 레버리지 적용 — Buy&Hold의 Nx판)'},
    'perfect':    {'label': '완벽예측(상한)', 'desc': '미래를 알고 투표'},
}


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
        if scenario == 'ma_cross':
            return gen_ma_cross(past, participants, coins)
        if scenario == 'always_long':
            return gen_always_long(participants, coins)
        if scenario == 'perfect':
            return gen_perfect(future, participants, coins)
        return gen_random(participants, seed=day_idx, coins=coins)

    return gen


def make_custom_generator(vote_stance, coins=None):
    """
    사용자 직접투표 모드: 고정 방향({coin: -2~+2})을 매 라운드 적용.
    "내가 이 포지션을 유지했다면 과거에 어땠을까"를 체험.
    """
    coins = coins or COINS
    stance = {c: int(vote_stance.get(c, 0)) for c in coins}

    def gen(day_idx, participants, past, future):
        for p in participants:
            for c in coins:
                p['votes'][c] = stance[c]
        return participants

    return gen
