"""
GovernanceFund 엔진 — 투표→비중 결정 + 백테스트 핵심 로직.

노트북(backtest/GovernanceFund_weight_decision/01,02.ipynb)에서 검증된 로직을
재사용 가능한 모듈로 추출. 백테스트 사이트와 AI Keeper의 공통 기반.
"""
from .profiles import VOLATILITY, COINS, FUND_PROFILES
from .alpha import adaptive_alpha
from .voting import simulate_votes, votes_to_target
from .prices import fetch_candles, fetch_closes, fetch_current_prices
from .scenarios import (
    score_to_vote,
    gen_momentum, gen_contrarian, gen_random, gen_perfect,
    make_generator,
)
from .backtest import run_backtest, calc_metrics

__all__ = [
    'VOLATILITY', 'COINS', 'FUND_PROFILES',
    'adaptive_alpha',
    'simulate_votes', 'votes_to_target',
    'fetch_candles', 'fetch_closes', 'fetch_current_prices',
    'score_to_vote', 'gen_momentum', 'gen_contrarian', 'gen_random',
    'gen_perfect', 'make_generator',
    'run_backtest', 'calc_metrics',
]
