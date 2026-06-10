"""투표주기 적응형 EMA 계수."""


def adaptive_alpha(period_days, T_converge_days, leftover=0.1):
    """
    투표주기에 반비례하는 EMA 계수를 반환.

    어떤 투표주기를 쓰든 'T_converge일 안에 (1-leftover)=90% 수렴'을 보장한다.

        alpha = 1 - leftover ^ (period_days / T_converge_days)

    - 주기가 길수록(주간) alpha↑ → 한 번에 확 반영
    - 주기가 짧을수록(일간) alpha↓ → 살살 반영하되 자주 누적
    → 결과적으로 '달력 기준' 반응속도는 동일.

    Args:
        period_days: 투표(리밸런싱) 주기, 일 단위.
        T_converge_days: 목표 비중 90% 도달 기간, 일 단위.
        leftover: 수렴기간 후 남길 비율 (기본 0.1 = 90% 수렴).

    Returns:
        float: EMA 계수 alpha (0~1).
    """
    period_days = max(period_days, 1e-9)
    return 1 - leftover ** (period_days / T_converge_days)
