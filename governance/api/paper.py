# -*- coding: utf-8 -*-
"""
페이퍼 트레이딩 상태 관리 (인메모리 MVP).

실제 돈 없이: 참여자 투표 → 목표 비중 → 실시간 HL 가격으로 가상 NAV 추적.
자산별 손익 기여, 평균단가, 청산가(추정)까지 계산.
※ MVP는 프로세스 메모리에 보관. 추후 SQLite/Postgres로 교체.
"""
import time

from governance.engine import (
    COINS, FUND_PROFILES, adaptive_alpha,
    simulate_votes, votes_to_target, fetch_current_prices,
    fetch_current_funding, fetch_asset_meta, liquidation_price,
)
from governance.engine.voting import apply_ema

_INITIAL = 100_000.0  # 펀드 기준 가상 자본


def _fresh_weights():
    return {c: 100.0 / len(COINS) for c in COINS}


_state = {
    "participants": {},
    "weights": _fresh_weights(),
    "fund_equity": _INITIAL,
    "asset_pnl": {c: 0.0 for c in COINS},   # 코인별 누적 손익($)
    "avg_entry": {c: None for c in COINS},  # 코인별 평균단가
    "last_prices": {},
    "nav_history": [],
    "profile": "aggressive",
    "last_target": None,
}


def reset():
    _state.update({
        "participants": {},
        "weights": _fresh_weights(),
        "fund_equity": _INITIAL,
        "asset_pnl": {c: 0.0 for c in COINS},
        "avg_entry": {c: None for c in COINS},
        "last_prices": {},
        "nav_history": [],
        "profile": "aggressive",
        "last_target": None,
    })


def _update_avg_entry(old_w, new_w, prices):
    """리밸런싱 시 코인별 평균단가 갱신 (거래소 방식 근사)."""
    for c in COINS:
        px = prices.get(c)
        if not px:
            continue
        ow, nw = old_w[c], new_w[c]
        cur = _state["avg_entry"][c]
        if abs(nw) < 1e-9:
            _state["avg_entry"][c] = None                      # 청산
        elif cur is None or (ow >= 0) != (nw >= 0):
            _state["avg_entry"][c] = px                        # 신규/방향전환
        elif abs(nw) > abs(ow):                                # 같은 방향 증액
            _state["avg_entry"][c] = (cur * abs(ow) + px * (abs(nw) - abs(ow))) / abs(nw)
        # 감액은 평균단가 유지


def _aggregate():
    ps = [{"deposit": p["deposit"], "votes": p["votes"]}
          for p in _state["participants"].values()]
    if not ps:
        return
    profile = FUND_PROFILES[_state["profile"]]
    target = votes_to_target(simulate_votes(ps, COINS), COINS)
    _state["last_target"] = target
    if target is None:
        return
    alpha = adaptive_alpha(7, profile["T_CONVERGE"])
    old_w = dict(_state["weights"])
    new_w = apply_ema(old_w, target, alpha, profile["MAX_WEIGHT"], COINS)
    prices = fetch_current_prices(COINS)
    if prices:
        _update_avg_entry(old_w, new_w, prices)
    _state["weights"] = new_w


def _mark_to_market():
    """실시간 HL 가격으로 평가 → fund_equity + 코인별 손익 갱신."""
    prices = fetch_current_prices(COINS)
    if not prices:
        return
    last = _state["last_prices"]
    lev = FUND_PROFILES[_state["profile"]]["FUND_LEVERAGE"]
    if last:
        eq = _state["fund_equity"]
        day_total = 0.0
        for c in COINS:
            if c in prices and c in last and last[c] > 0:
                ret = prices[c] / last[c] - 1
                pnl = (_state["weights"][c] / 100) * eq * lev * ret
                _state["asset_pnl"][c] += pnl
                day_total += pnl
        _state["fund_equity"] = max(eq + day_total, 0)
    _state["last_prices"] = prices
    # 평균단가가 아직 없으면 현재가로 초기화 (최초 진입)
    for c in COINS:
        if _state["avg_entry"][c] is None and abs(_state["weights"][c]) > 1e-9:
            _state["avg_entry"][c] = prices.get(c)
    eq = _state["fund_equity"]
    _state["nav_history"].append({
        "t": int(time.time()),
        "value": round(eq, 2),
        "ret_pct": round((eq / _INITIAL - 1) * 100, 3),
    })
    if len(_state["nav_history"]) > 2000:
        _state["nav_history"] = _state["nav_history"][-2000:]


def submit_vote(user, deposit, votes, profile):
    votes = {c: int(votes.get(c, 0)) for c in COINS}
    _state["participants"][user] = {"deposit": float(deposit),
                                    "votes": votes, "profile": profile}
    _state["profile"] = profile
    _aggregate()
    _mark_to_market()


def get_state():
    _mark_to_market()
    total_dep = sum(p["deposit"] for p in _state["participants"].values())
    eq = _state["fund_equity"]
    profile = FUND_PROFILES[_state["profile"]]
    lev = profile["FUND_LEVERAGE"]

    participants = []
    for user, p in _state["participants"].items():
        share = p["deposit"] / total_dep if total_dep else 0
        participants.append({
            "user": user, "deposit": p["deposit"],
            "share_pct": round(share * 100, 1), "votes": p["votes"],
            "paper_value": round(eq * share, 2),
            "ret_pct": round((eq / _INITIAL - 1) * 100, 2),
        })
    participants.sort(key=lambda x: x["paper_value"], reverse=True)

    cf = fetch_current_funding(COINS)
    meta = fetch_asset_meta(COINS)
    prices = _state["last_prices"]

    carry_annual = 0.0
    carry_by_coin, assets = {}, {}
    for c in COINS:
        w = _state["weights"][c]
        ann = cf.get(c, {}).get("annual_pct", 0)
        contrib = -(w / 100) * lev * ann
        carry_by_coin[c] = round(contrib, 2)
        carry_annual += contrib

        entry = _state["avg_entry"][c]
        side = "long" if w >= 0 else "short"
        mmr = meta.get(c, {}).get("mmr", 0.02)
        liq = (liquidation_price(entry, lev, side, mmr)
               if entry and abs(w) > 1e-9 and lev > 1 else None)
        px = prices.get(c)
        liq_dist = (round(abs(px - liq) / px * 100, 1)
                    if liq and px else None)
        assets[c] = {
            "weight": round(w, 1),
            "return_pct": round(_state["asset_pnl"][c] / _INITIAL * 100, 2),
            "funding_carry": round(contrib, 2),
            "avg_entry": round(entry, 2) if entry else None,
            "price": px,
            "liq_price": round(liq, 2) if liq else None,
            "liq_dist_pct": liq_dist,
            "max_leverage": meta.get(c, {}).get("max_leverage"),
        }

    return {
        "profile": _state["profile"], "leverage": lev,
        "fund_equity": round(eq, 2),
        "fund_return_pct": round((eq / _INITIAL - 1) * 100, 2),
        "funding_carry_annual_pct": round(carry_annual, 2),
        "funding_carry_by_coin": carry_by_coin,
        "funding_rates": {c: cf.get(c, {}).get("annual_pct", 0) for c in COINS},
        "weights": {c: round(_state["weights"][c], 1) for c in COINS},
        "assets": assets,
        "target": (None if _state["last_target"] is None
                   else {c: round(_state["last_target"][c], 1) for c in COINS}),
        "participants": participants,
        "nav_history": _state["nav_history"][-300:],
        "prices": prices,
    }
