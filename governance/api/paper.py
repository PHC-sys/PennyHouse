# -*- coding: utf-8 -*-
"""
페이퍼 트레이딩 상태 관리 (인메모리 MVP).

실제 돈 없이: 참여자 투표 → 목표 비중 → 실시간 HL 가격으로 가상 NAV 추적.
※ MVP는 프로세스 메모리에 보관. 추후 SQLite/Postgres로 교체.
"""
import time

from governance.engine import (
    COINS, FUND_PROFILES, adaptive_alpha,
    simulate_votes, votes_to_target, fetch_current_prices,
    fetch_current_funding,
)
from governance.engine.voting import apply_ema

_INITIAL = 100_000.0  # 펀드 기준 가상 자본

_state = {
    "participants": {},          # user -> {deposit, votes, profile}
    "weights": {c: 100.0 / len(COINS) for c in COINS},  # 부호 있는 비중
    "fund_equity": _INITIAL,
    "last_prices": {},
    "nav_history": [],           # [{t, value, ret_pct}]
    "profile": "aggressive",
    "last_target": None,
}


def reset():
    _state["participants"] = {}
    _state["weights"] = {c: 100.0 / len(COINS) for c in COINS}
    _state["fund_equity"] = _INITIAL
    _state["last_prices"] = {}
    _state["nav_history"] = []
    _state["profile"] = "aggressive"
    _state["last_target"] = None


def _aggregate():
    """현 참여자 투표 → 목표 비중 + EMA 한 스텝 적용."""
    ps = [{"deposit": p["deposit"], "votes": p["votes"]}
          for p in _state["participants"].values()]
    if not ps:
        return
    profile = FUND_PROFILES[_state["profile"]]
    target = votes_to_target(simulate_votes(ps, COINS), COINS)
    _state["last_target"] = target
    if target is None:
        return
    # 투표 라운드를 주간(7일)처럼 강하게 반영
    alpha = adaptive_alpha(7, profile["T_CONVERGE"])
    _state["weights"] = apply_ema(_state["weights"], target, alpha,
                                  profile["MAX_WEIGHT"], COINS)


def _mark_to_market():
    """실시간 HL 가격으로 가상 포지션 평가 → fund_equity 갱신."""
    prices = fetch_current_prices(COINS)
    if not prices:
        return
    last = _state["last_prices"]
    profile = FUND_PROFILES[_state["profile"]]
    lev = profile["FUND_LEVERAGE"]
    if last:
        pnl = 0.0
        for c in COINS:
            if c in prices and c in last and last[c] > 0:
                ret = prices[c] / last[c] - 1
                pnl += (_state["weights"][c] / 100) * _state["fund_equity"] * lev * ret
        _state["fund_equity"] = max(_state["fund_equity"] + pnl, 0)
    _state["last_prices"] = prices
    eq = _state["fund_equity"]
    _state["nav_history"].append({
        "t": int(time.time()),
        "value": round(eq, 2),
        "ret_pct": round((eq / _INITIAL - 1) * 100, 3),
    })
    # 히스토리 길이 제한
    if len(_state["nav_history"]) > 2000:
        _state["nav_history"] = _state["nav_history"][-2000:]


def submit_vote(user, deposit, votes, profile):
    votes = {c: int(votes.get(c, 0)) for c in COINS}
    _state["participants"][user] = {"deposit": float(deposit),
                                    "votes": votes, "profile": profile}
    _state["profile"] = profile  # 펀드 프로파일 = 최신 제출값
    _aggregate()
    _mark_to_market()


def get_state():
    _mark_to_market()  # 조회 시점 mark-to-market
    total_dep = sum(p["deposit"] for p in _state["participants"].values())
    eq = _state["fund_equity"]
    participants = []
    for user, p in _state["participants"].items():
        share = p["deposit"] / total_dep if total_dep else 0
        participants.append({
            "user": user, "deposit": p["deposit"],
            "share_pct": round(share * 100, 1),
            "votes": p["votes"],
            "paper_value": round(eq * share, 2),
            "ret_pct": round((eq / _INITIAL - 1) * 100, 2),
        })
    participants.sort(key=lambda x: x["paper_value"], reverse=True)

    # 펀딩 캐리 (연환산 %): 롱은 펀딩 지불(-), 숏은 수취(+)
    lev = FUND_PROFILES[_state["profile"]]["FUND_LEVERAGE"]
    cf = fetch_current_funding(COINS)
    carry_annual = 0.0
    carry_by_coin = {}
    for c in COINS:
        ann = cf.get(c, {}).get("annual_pct", 0)
        contrib = -(_state["weights"][c] / 100) * lev * ann  # 롱(+w)→비용
        carry_by_coin[c] = round(contrib, 2)
        carry_annual += contrib

    return {
        "profile": _state["profile"],
        "fund_equity": round(eq, 2),
        "fund_return_pct": round((eq / _INITIAL - 1) * 100, 2),
        "funding_carry_annual_pct": round(carry_annual, 2),
        "funding_carry_by_coin": carry_by_coin,
        "funding_rates": {c: cf.get(c, {}).get("annual_pct", 0) for c in COINS},
        "weights": {c: round(_state["weights"][c], 1) for c in COINS},
        "target": (None if _state["last_target"] is None
                   else {c: round(_state["last_target"][c], 1) for c in COINS}),
        "participants": participants,
        "nav_history": _state["nav_history"][-300:],
        "prices": _state["last_prices"],
    }
