"""펀드 프로파일 및 코인 설정."""

# 코인별 일간 변동성 (실측 근사). vol_factor 계산에 사용.
VOLATILITY = {
    'BTC':  0.030,
    'ETH':  0.040,
    'SOL':  0.055,
    'HYPE': 0.070,
}
COINS = list(VOLATILITY.keys())

# 펀드 프로파일
#   T_CONVERGE     : 목표 비중 90% 도달까지 걸리는 '달력 일수'
#                    (alpha는 투표주기에서 자동 계산 → adaptive_alpha)
#   MAX_WEIGHT     : 코인 1종 최대 비중 (롱/숏 공통, 독식 방지)
#   FUND_LEVERAGE  : 전체 포트폴리오 레버리지 배수
FUND_PROFILES = {
    'aggressive':   {'T_CONVERGE': 7,  'MAX_WEIGHT': 80, 'FUND_LEVERAGE': 5, 'color': '#e74c3c'},
    'conservative': {'T_CONVERGE': 21, 'MAX_WEIGHT': 60, 'FUND_LEVERAGE': 2, 'color': '#2ecc71'},
    'spot':         {'T_CONVERGE': 14, 'MAX_WEIGHT': 70, 'FUND_LEVERAGE': 1, 'color': '#5b8def'},
}

# 백테스트 수수료 (HL Perp maker 왕복)
MAKER_FEE = 0.00010
REBALANCE_FEE = MAKER_FEE * 2
