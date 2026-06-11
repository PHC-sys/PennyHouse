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

import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
    fetch_universe, compute_volatility, asset_sparkline, batch_sparklines,
)
from governance.engine.voting import apply_ema
from governance.api import paper
from governance.api import live

app = FastAPI(title="GovernanceFund Backtest & Paper Trading")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    live.start_worker()  # HL WebSocket 라이브 가격 워커 기동


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


@app.get("/api/assets")
def get_assets(category: Optional[str] = None, sub: Optional[str] = None,
               search: Optional[str] = None, limit: int = 500):
    """전 자산 레지스트리 (Crypto/TradFi/Pre-IPO). 필터 지원."""
    full = fetch_universe()
    counts = {}
    for a in full:
        counts[a["category"]] = counts.get(a["category"], 0) + 1

    uni = full
    if search:
        q = search.upper()
        uni = [a for a in uni if q in a["display"].upper()]
    elif category:
        uni = [a for a in uni if a["category"] == category]
        if sub:
            uni = [a for a in uni if a["sub"] == sub]
        uni = uni[:limit]
    else:
        # '전체'는 카테고리 골고루 인터리브 (크립토만 깔리는 문제 방지)
        buckets = {}
        for a in full:
            buckets.setdefault(a["category"], []).append(a)
        order = ["crypto", "tradfi", "preipo"]
        mixed, idx = [], 0
        while len(mixed) < limit and any(idx < len(buckets.get(c, [])) for c in order):
            for c in order:
                b = buckets.get(c, [])
                if idx < len(b):
                    mixed.append(b[idx])
            idx += 1
        uni = mixed[:limit]
    return {"counts": counts, "total": len(full), "assets": uni}


@app.get("/api/spark/{symbol:path}")
def get_spark(symbol: str, days: int = 30):
    """미니 차트용 종가 스파크라인 (HIP-3 prefix 'xyz:NVDA' 지원)."""
    return {"symbol": symbol, "series": asset_sparkline(symbol, days=days),
            "volatility": compute_volatility(symbol)}


class SparkBatchReq(BaseModel):
    symbols: list[str]
    days: int = 14


@app.post("/api/sparks")
def post_sparks(req: SparkBatchReq):
    """여러 심볼 스파크라인 일괄 (마켓 타일 로딩 안정화)."""
    return {"sparks": batch_sparklines(req.symbols[:150], days=req.days)}


@app.get("/api/prices/{coin:path}")
def get_prices(coin: str, days: int = 90, interval: str = "1d"):
    coin = coin if ":" in coin else coin.upper()  # HIP-3 prefix 보존
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


@app.get("/api/funding/{coin:path}")
def get_funding(coin: str, days: int = 90):
    coin = coin if ":" in coin else coin.upper()
    df = fetch_funding_history(coin, days=days)
    cur = fetch_current_funding([coin]).get(coin, {})
    if df is None:
        raise HTTPException(404, f"{coin} 펀딩 데이터 없음")
    series = [{"time": int(ts.timestamp()),
               "value": round(float(r.fundingRate) * 24 * 365 * 100, 3)}
              for ts, r in df.iterrows()]
    return {"coin": coin, "current": cur, "series": series}


@app.get("/api/current_funding")
def get_current_funding():
    return fetch_current_funding(COINS)


@app.get("/api/live")
def get_live(symbols: Optional[str] = None):
    """라이브 가격 스냅샷 (REST 폴백). symbols=쉼표구분."""
    syms = symbols.split(",") if symbols else None
    return {"mids": live.get_mids(syms), "status": live.status()}


@app.websocket("/ws/market")
async def ws_market(ws: WebSocket):
    """라이브 가격 푸시. 클라이언트가 보낸 symbols만 변경분 전송."""
    await ws.accept()
    watch = None  # None=전체
    last = {}
    try:
        # 첫 메시지로 관심 심볼 받기 (없으면 전체)
        try:
            init = await asyncio.wait_for(ws.receive_json(), timeout=0.5)
            if isinstance(init, dict) and init.get("symbols"):
                watch = list(init["symbols"])
        except (asyncio.TimeoutError, Exception):
            pass

        while True:
            mids = live.get_mids(watch)
            diff = {s: p for s, p in mids.items() if last.get(s) != p}
            if diff:
                await ws.send_json({"mids": diff})
                last.update(diff)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception:
        return


@app.get("/api/relative")
def get_relative(a: str, b: str, days: int = 180, interval: str = "1d"):
    """상대가격 A/B. HIP-3 prefix는 쿼리파라미터로 안전하게 전달."""
    a = a if ":" in a else a.upper()
    b = b if ":" in b else b.upper()
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
