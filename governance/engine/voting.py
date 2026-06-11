"""투표 집계 및 목표 비중 산출 (Target 방식)."""

from .profiles import VOLATILITY, COINS


def simulate_votes(participants, coins=None):
    """
    참여자 투표를 예치금 가중평균으로 집계.

    Args:
        participants: [{'deposit': float, 'votes': {coin: int(-2~+2)}}, ...]
        coins: 대상 코인 리스트 (기본 COINS).

    Returns:
        {coin: {'score': float(-1~+1)}}  예치금 가중 score.
    """
    coins = coins or COINS
    total = sum(p['deposit'] for p in participants)
    if total <= 0:
        return {c: {'score': 0.0} for c in coins}
    results = {}
    for c in coins:
        ws = sum(p['votes'].get(c, 0) * p['deposit'] / total for p in participants)
        results[c] = {'score': ws / 2}  # -2~+2 → -1~+1 정규화
    return results


def votes_to_target(vote_result, coins=None, vol_map=None):
    """
    집단 투표 score → 목표 비중 (부호 있음, Target 방식).

      target[coin] = score × vol_factor
      정규화: sum(abs) = 100  (gross exposure 100%)
      vol_factor = 0.03 / 코인변동성  (변동성 큰 코인은 작게)

    score가 곧바로 목표 포지션을 결정 → 숏도 즉시 진입 가능.

    Args:
        vote_result: simulate_votes() 결과.
        coins: 대상 코인 리스트.
        vol_map: {symbol: 변동성} (임의 유니버스용). 없으면 기본 VOLATILITY.

    Returns:
        {coin: float}  부호 있는 목표 비중(%). 양수=롱, 음수=숏.
        신호 없음(all hold)이면 None.
    """
    coins = coins or COINS
    vm = vol_map or VOLATILITY
    raw = {}
    for c in coins:
        score = vote_result[c]['score']
        vol_factor = 0.03 / (vm.get(c) or 0.05)
        raw[c] = score * vol_factor

    total_abs = sum(abs(v) for v in raw.values())
    if total_abs < 1e-9:
        return None
    return {c: raw[c] / total_abs * 100 for c in coins}


def apply_ema(current_weights, target, alpha, max_weight, coins=None):
    """
    EMA로 현재 비중을 목표 비중 쪽으로 한 스텝 이동.

    Args:
        current_weights: {coin: float} 현재 비중(부호 있음).
        target: {coin: float} 목표 비중. None이면 현 비중 유지.
        alpha: EMA 계수 (adaptive_alpha 결과).
        max_weight: 코인별 절대 비중 상한.
        coins: 대상 코인.

    Returns:
        {coin: float} 갱신된 비중(부호 있음, ±max_weight 클립).
    """
    coins = coins or COINS
    if target is None:
        return dict(current_weights)
    out = {}
    for c in coins:
        v = alpha * target[c] + (1 - alpha) * current_weights[c]
        out[c] = max(-max_weight, min(max_weight, v))
    return out
