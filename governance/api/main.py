# -*- coding: utf-8 -*-
"""
GovernanceFund 백테스트 & 페이퍼 트레이딩 API.

엔드포인트:
  GET  /api/config                  코인/프로파일 메타
  GET  /api/prices/{coin}           HL 캔들 (차트용)
  POST /api/backtest                투표 시나리오 백테스트
  POST /api/paper/vote              페이퍼 투표 제출
  GET  /api/paper/state             페이퍼 펀드 현황 + NAV
  POST /api/paper/reset             페이퍼 세션 초기화
정적 프론트는 /  에서 서빙.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from governance.engine import (
    COINS, VOLATILITY, FUND_PROFILES, SCENARIO_META,
    adaptive_alpha, simulate_votes, votes_to_target,
    fetch_candles, fetch_closes, fetch_current_prices,
    fetch_funding_history, fetch_current_funding, relative_series,
    make_generator, make_custom_generator, run_backtest, calc_metrics,
)
from governance.engine.voting import apply_ema
from governance.api import paper

app = FastAPI(title="GovernanceFund Backtest & Paper Trading")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ────────────────────────────────────────────────────────────────
# 메타
# ────────────────────────────────────────────────────────────────
@app.get("/api/config")
def get_config():
    return {
        "coins": COINS,
        "volatility": VOLATILITY,
        "profiles": {
            k: {"T_CONVERGE": v["T_CONVERGE"], "MAX_WEIGHT": v["MAX_WEIGHT"],
                "FUND_LEVERAGE": v["FUND_LEVERAGE"], "color": v["color"],
                "alpha_weekly": round(adaptive_alpha(7, v["T_CONVERGE"]), 3)}
            for k, v in FUND_PROFILES.items()
        },
    }


@app.get("/api/scenarios")
def get_scenarios():
    return SCENARIO_META


@app.get("/api/prices/{coin}")
def get_prices(coin: str, days: int = 90, interval: str = "1d"):
    coin = coin.upper()
    df = fetch_candles(coin, days=days, interval=interval)
    if df is None:
        raise HTTPException(404, f"{coin} 데이터 없음")
    return {
        "coin": coin, "interval": interval,
        "candles": [
            {"time": int(ts.timestamp()), "open": r.open, "high": r.high,
             "low": r.low, "close": r.close, "volume": r.volume}
            for ts, r in df.iterrows()
        ],
    }


@app.get("/api/funding/{coin}")
def get_funding(coin: str, days: int = 90):
    coin = coin.upper()
    df = fetch_funding_history(coin, days=days)
    cur = fetch_current_funding([coin]).get(coin, {})
    if df is None:
        raise HTTPException(404, f"{coin} 펀딩 데이터 없음")
    # 8시간 누적을 일 단위로 리샘플해 연환산(%) 시계열
    series = [{"time": int(ts.timestamp()),
               "value": round(float(r.fundingRate) * 24 * 365 * 100, 3)}
              for ts, r in df.iterrows()]
    return {"coin": coin, "current": cur, "series": series}


@app.get("/api/current_funding")
def get_current_funding():
    return fetch_current_funding(COINS)


@app.get("/api/relative/{coin_a}/{coin_b}")
def get_relative(coin_a: str, coin_b: str, days: int = 180, interval: str = "1d"):
    a, b = coin_a.upper(), coin_b.upper()
    series = relative_series(a, b, days=days, interval=interval)
    if not series:
        raise HTTPException(404, "상대가격 데이터 없음")
    return {"pair": f"{a}/{b}", "series": series}


# ────────────────────────────────────────────────────────────────
# 백테스트
# ────────────────────────────────────────────────────────────────
class BacktestReq(BaseModel):
    profile: str = "aggressive"
    days: int = 180
    rebalance_every: int = 7
    scenarios: list[str] = ["momentum", "contrarian", "ma_cross", "random", "perfect"]
    custom_votes: Optional[dict] = None  # {coin:-2~+2} → '내 스탠스' 시나리오 추가


@app.post("/api/backtest")
def post_backtest(req: BacktestReq):
    if req.profile not in FUND_PROFILES:
        raise HTTPException(400, "알 수 없는 프로파일")
    closes, returns = fetch_closes(days=req.days)
    if returns is None:
        raise HTTPException(503, "HL 가격 수집 실패")

    dates = [int(ts.timestamp()) for ts in returns.index]
    bh_equity = (1 + returns.mean(axis=1)).cumprod()
    bh_cum = ((bh_equity / bh_equity.iloc[0]) - 1) * 100

    out = {"dates": dates,
           "benchmark": {"label": "Buy & Hold", "cum_return": [round(x, 2) for x in bh_cum]},
           "scenarios": {}, "metrics": {}, "labels": {}}

    jobs = [(s, make_generator(s)) for s in req.scenarios]
    if req.custom_votes:
        jobs.append(("custom", make_custom_generator(req.custom_votes)))

    for s, gen in jobs:
        df = run_backtest(s, gen, returns, req.profile,
                          rebalance_every=req.rebalance_every)
        out["scenarios"][s] = {
            "cum_return": [round(x, 2) for x in df["cum_return"]],
            "drawdown": [round(x, 2) for x in df["drawdown"]],
            "weights": {c: [round(x, 1) for x in df[f"w_{c}"]] for c in COINS},
            "asset_contribution": df.attrs.get("asset_contribution", {}),
        }
        out["metrics"][s] = calc_metrics(df)
        out["labels"][s] = (SCENARIO_META.get(s, {}).get("label")
                            or ("내 스탠스" if s == "custom" else s))

    out["metrics"]["benchmark"] = {
        "cum_return": round(bh_cum.iloc[-1], 1),
        "max_drawdown": round((bh_equity / bh_equity.cummax() - 1).min() * 100, 1),
    }
    out["alpha"] = round(adaptive_alpha(req.rebalance_every,
                                        FUND_PROFILES[req.profile]["T_CONVERGE"]), 3)
    return out


# ────────────────────────────────────────────────────────────────
# 페이퍼 트레이딩
# ────────────────────────────────────────────────────────────────
class VoteReq(BaseModel):
    user: str
    deposit: float = 10000
    votes: dict  # {coin: int(-2~+2)}
    profile: str = "aggressive"


@app.post("/api/paper/vote")
def post_vote(req: VoteReq):
    if req.profile not in FUND_PROFILES:
        raise HTTPException(400, "알 수 없는 프로파일")
    paper.submit_vote(req.user, req.deposit, req.votes, req.profile)
    return paper.get_state()


@app.get("/api/paper/state")
def get_paper_state():
    return paper.get_state()


@app.post("/api/paper/reset")
def reset_paper():
    paper.reset()
    return paper.get_state()


# ────────────────────────────────────────────────────────────────
# 정적 프론트 (맨 마지막에 마운트)
# ────────────────────────────────────────────────────────────────
_web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if os.path.isdir(_web_dir):
    app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web")
