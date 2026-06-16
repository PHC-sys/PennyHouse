# -*- coding: utf-8 -*-
"""
GovernanceFund 백테스트 & 페이퍼 트레이딩 API.

주요 엔드포인트:
  GET  /api/config /api/scenarios /api/assets        메타/자산 레지스트리
  GET  /api/prices/{sym} /api/funding/{sym} /api/relative  차트
  GET  /api/live  WS /ws/market                      라이브 가격
  POST /api/backtest                                 백테스트
  CRUD /api/funds, /api/funds/{id}/vote|state|reset  멀티펀드
프론트는 Next.js(governance/web-next, :3010)가 /api/* 프록시.
"""
import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
from governance.api import live
from governance.api import store
from governance.api import funds as funds_engine
import uuid

app = FastAPI(title="GovernanceFund Backtest & Paper Trading")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    live.start_worker()  # HL WebSocket 라이브 가격 워커 기동
    store.init_db()
    _seed_demo_fund()
    threading.Thread(target=_prewarm_loop, daemon=True, name='fund-prewarm').start()


def _prewarm_loop():
    """백그라운드 투영 워커 — 전 펀드를 주기적으로 재구성해 캐시를 따뜻하게 유지.
    덕분에 목록/상세 서빙은 항상 웜 캐시를 읽어 즉시 응답(콜드 스타트 제거).
    수집(live 워커)·투영(여기)·서빙(API)을 분리하는 패턴."""
    time.sleep(3)  # 라이브 워커가 mids 채울 시간
    while True:
        try:
            for f in store.list_funds():
                try:
                    funds_engine.get_state(f)  # 재구성 → 캔들/nav 캐시 예열
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(45)


def _seed_demo_fund():
    """첫 실행 시 Demo 펀드 1개 자동 생성 (빈 목록 방지)."""
    if store.list_funds():
        return
    store.create_fund({
        'id': 'demo-' + uuid.uuid4().hex[:8],
        'name': 'Demo 펀드 — 자유 체험',
        'kind': 'demo', 'visibility': 'public', 'creator': None,
        'profile': 'aggressive', 'leverage': None,
        'initial_deposit': 100000, 'max_deposit': None,
        'universe': ['BTC', 'ETH', 'SOL', 'HYPE'],
        'init_weights': {}, 'allowlist': [],
    })


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


@app.websocket("/ws/asset/{coin:path}")
async def ws_asset(ws: WebSocket, coin: str):
    """포커스된 자산만 실시간 ctx(펀딩/마크/OI/거래량) 푸시 — 거래소 방식."""
    await ws.accept()
    live.subscribe_ctx(coin)
    last = None
    try:
        while True:
            ctx = live.get_ctx(coin)
            if ctx and ctx != last:
                await ws.send_json({"ctx": ctx})
                last = ctx
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        live.unsubscribe_ctx(coin)


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
# 멀티펀드 CRUD
# ────────────────────────────────────────────────────────────────
class CreateFundReq(BaseModel):
    name: str
    kind: str = "demo"            # demo | real
    visibility: str = "public"    # public | private
    creator: Optional[str] = None
    profile: str = "aggressive"
    leverage: Optional[int] = None
    initial_deposit: float = 100000
    max_deposit: Optional[float] = None
    universe: list[str] = ["BTC", "ETH", "SOL", "HYPE"]
    init_weights: Optional[dict] = None
    allowlist: list[str] = []


def _fund_summary(f, votes_count_map, nav_last):
    """목록용 요약 (TVL/참여자/수익률)."""
    fid = f["id"]
    return {
        **f,
        "allowlist": None,  # 목록엔 미노출
        "participants": votes_count_map.get(fid, 0),
        "nav_ret_pct": nav_last.get(fid),
    }


@app.post("/api/funds")
def create_fund(req: CreateFundReq):
    if req.kind not in ("demo", "real"):
        raise HTTPException(400, "kind는 demo|real")
    if req.profile not in FUND_PROFILES:
        raise HTTPException(400, "알 수 없는 프로파일")
    if not req.universe:
        raise HTTPException(400, "운용 자산을 1개 이상 선택")
    if len(req.universe) > 10:
        raise HTTPException(400, "운용 자산은 최대 10종까지")
    fid = ("demo" if req.kind == "demo" else "fund") + "-" + uuid.uuid4().hex[:8]
    store.create_fund({"id": fid, **req.dict()})
    return store.get_fund(fid)


@app.get("/api/funds")
def list_funds(user: Optional[str] = None):
    funds = store.list_funds()
    vc, nv, fc = {}, {}, {}
    for f in funds:
        vc[f["id"]] = len(store.get_votes(f["id"]))
        try:
            st = funds_engine.get_state(f)  # 라이브 수익률 + 펀딩캐리
            nv[f["id"]] = st["fund_return_pct"]
            fc[f["id"]] = st["funding_carry_annual_pct"]
        except Exception:
            nav = store.get_nav(f["id"], limit=1)
            nv[f["id"]] = nav[-1]["ret_pct"] if nav else None
            fc[f["id"]] = None
    mine = store.funds_for_user(user) if user else set()

    out = []
    for f in funds:
        s = _fund_summary(f, vc, nv)
        s["funding_carry_annual_pct"] = fc.get(f["id"])
        out.append(s)
    # 정렬: 내 펀드 → demo → 최신
    def sort_key(s):
        return (0 if s["id"] in mine else 1,
                0 if s["kind"] == "demo" else 1,
                -s["created_at"])
    out.sort(key=sort_key)
    for s in out:
        s["is_mine"] = s["id"] in mine
    return {"funds": out}


@app.get("/api/funds/{fund_id}")
def get_fund(fund_id: str):
    f = store.get_fund(fund_id)
    if not f:
        raise HTTPException(404, "펀드 없음")
    f["allowlist"] = store.get_allowlist(fund_id)
    f["participants"] = len(store.get_votes(fund_id))
    return f


@app.delete("/api/funds/{fund_id}")
def remove_fund(fund_id: str, user: Optional[str] = None):
    """펀드 삭제 — 생성자만, 자금이 0일 때만 (전원 회수/청산 후)."""
    f = store.get_fund(fund_id)
    if not f:
        raise HTTPException(404, "펀드 없음")
    if f.get("creator") and user != f["creator"]:
        raise HTTPException(403, "펀드 생성자만 삭제할 수 있어요")
    total_dep = sum(v["deposit"] for v in store.get_votes(fund_id))
    equity = funds_engine.current_equity(f)
    if total_dep > 0 and equity > 1e-6:
        raise HTTPException(400, "자금이 남아 있어 삭제할 수 없어요 — 참가자 전원 회수 후 가능")
    store.delete_fund(fund_id)
    funds_engine.drop_runtime(fund_id)
    return {"ok": True}


class RedeemReq(BaseModel):
    user: str


@app.post("/api/funds/{fund_id}/redeem")
def fund_redeem(fund_id: str, req: RedeemReq):
    """참가자 지분 회수(출금/탈퇴). 그의 share만큼 인출하고 투표 삭제."""
    f = store.get_fund(fund_id)
    if not f:
        raise HTTPException(404, "펀드 없음")
    res = funds_engine.redeem(f, req.user)
    if res is None:
        raise HTTPException(400, "이 펀드에 예치(투표) 내역이 없어요")
    state = funds_engine.get_state(f)
    return {**state, "redeemed": res["redeemed"], "remaining": res["remaining"]}


class FundVoteReq(BaseModel):
    user: str
    deposit: float = 10000
    votes: dict


@app.post("/api/funds/{fund_id}/vote")
def fund_vote(fund_id: str, req: FundVoteReq):
    f = store.get_fund(fund_id)
    if not f:
        raise HTTPException(404, "펀드 없음")
    funds_engine.submit_vote(f, req.user, req.deposit, req.votes)
    return funds_engine.get_state(f)


@app.get("/api/funds/{fund_id}/state")
def fund_state(fund_id: str):
    f = store.get_fund(fund_id)
    if not f:
        raise HTTPException(404, "펀드 없음")
    return funds_engine.get_state(f)


@app.post("/api/funds/{fund_id}/reset")
def fund_reset(fund_id: str):
    f = store.get_fund(fund_id)
    if not f:
        raise HTTPException(404, "펀드 없음")
    funds_engine.reset_fund(f)
    return funds_engine.get_state(f)


# 프론트는 Next.js(governance/web-next, :3010)가 담당.
# 단일 페이퍼(api/paper.py)·정적 web/는 멀티펀드(api/funds.py)로 대체되어 제거됨.
