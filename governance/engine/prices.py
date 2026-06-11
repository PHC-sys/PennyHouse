"""Hyperliquid 가격/캔들/펀딩 데이터 수집."""

import time
import threading
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .profiles import COINS

HL_API = 'https://api.hyperliquid.xyz/info'

# HL API rate limit 보호: 동시 요청 수 제한
_HL_SEM = threading.Semaphore(8)
_HL_SESSION = requests.Session()

# interval → 밀리초 (페이지네이션 계산용)
_INTERVAL_MS = {
    '1m': 60_000, '5m': 300_000, '15m': 900_000, '1h': 3_600_000,
    '4h': 14_400_000, '1d': 86_400_000, '1w': 604_800_000,
}

# 간단한 인메모리 캐시
_CACHE = {}
_CACHE_TTL = 300  # 5분


def _post(payload, timeout=15, retries=2):
    """HL POST. 동시성 제한 + 가벼운 재시도(일시적 실패/throttle 대응)."""
    for attempt in range(retries + 1):
        try:
            with _HL_SEM:
                r = _HL_SESSION.post(HL_API, json=payload, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        if attempt < retries:
            time.sleep(0.4 * (attempt + 1))  # 백오프
    return None


def fetch_candles(coin, days=180, interval='1d', use_cache=True, max_points=5000):
    """
    HL candleSnapshot으로 OHLCV 수집. HL은 요청당 약 5000개 제한 →
    필요 시 자동 페이지네이션으로 더 긴 기간도 수집.

    Returns:
        pd.DataFrame[open,high,low,close,volume] (UTC 인덱스), 실패 시 None.
    """
    key = (coin, interval, days)
    if use_cache and key in _CACHE:
        ts, df = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return df.copy()

    step = _INTERVAL_MS.get(interval, 86_400_000)
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 86_400_000

    all_rows = []
    cur_end = end_ms
    # 역방향으로 페이지네이션 (오래된 쪽으로)
    for _ in range(20):  # 안전 상한 (최대 20페이지)
        batch = _post({
            'type': 'candleSnapshot',
            'req': {'coin': coin, 'interval': interval,
                    'startTime': start_ms, 'endTime': cur_end},
        })
        if not batch:
            break
        all_rows = batch + all_rows  # 앞에 붙임
        if len(batch) < max_points or batch[0]['t'] <= start_ms:
            break
        cur_end = batch[0]['t'] - 1
        if cur_end <= start_ms:
            break

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    df['time'] = pd.to_datetime(df['t'], unit='ms', utc=True)
    df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low',
                            'c': 'close', 'v': 'volume'})
    df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
    df = df.drop_duplicates('time').set_index('time').astype(float).sort_index()

    _CACHE[key] = (time.time(), df.copy())
    return df


def fetch_closes(coins=None, days=180, interval='1d'):
    """여러 코인 종가 정렬 + 일간수익률. → (closes_df, returns_df)."""
    coins = coins or COINS
    data = {}
    for c in coins:
        df = fetch_candles(c, days=days, interval=interval)
        if df is not None and len(df) > 5:
            data[c] = df['close']
    if not data:
        return None, None
    closes = pd.DataFrame(data).dropna()
    returns = closes.pct_change().fillna(0)
    return closes, returns


_LIVE_CACHE = {}      # key → (ts, value)
_LIVE_TTL = 20        # 실시간 데이터 20초 캐시 (폴링 부하 완화)


def _live_cached(key, ttl, fn):
    now = time.time()
    if key in _LIVE_CACHE:
        ts, val = _LIVE_CACHE[key]
        if now - ts < ttl:
            return val
    val = fn()
    _LIVE_CACHE[key] = (now, val)
    return val


def fetch_current_prices(coins=None):
    """HL allMids로 현재가 (20초 캐시). → {coin: float}."""
    coins = coins or COINS

    def _f():
        mids = _post({'type': 'allMids'})
        return {c: float(mids[c]) for c in coins if c in mids} if mids else {}

    return _live_cached(('mids', tuple(coins)), _LIVE_TTL, _f)


def fetch_funding_history(coin, days=90):
    """
    HL fundingHistory로 펀딩비 시계열 수집.
    8시간마다 1건, 요청당 500건 제한(약 166일) → 페이지네이션으로 긴 기간 수집.

    Returns:
        pd.DataFrame[fundingRate] (UTC 인덱스), 실패 시 None.
        fundingRate = 1시간 지급요율. 연환산 = ×24×365.
        ※ HL 보관 기간/상장 시점까지만 — 요청보다 짧을 수 있음(정상).
    """
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 86_400_000
    all_rows = []
    cur_start = start_ms
    # 시간당 1건 → days일은 약 days*24/500 페이지 + 여유
    max_pages = max(3, days * 24 // 480 + 5)
    last_ts = None
    empty_streak = 0
    for _ in range(max_pages):
        batch = _post({'type': 'fundingHistory', 'coin': coin,
                       'startTime': cur_start, 'endTime': end_ms})
        if not batch:
            # 일시적 실패일 수 있음 — 한 번 더 시도 후 그래도 비면 종료
            empty_streak += 1
            if empty_streak >= 2:
                break
            time.sleep(0.3)
            continue
        empty_streak = 0
        all_rows += batch
        new_end = batch[-1]['time']
        if new_end == last_ts or new_end + 1 >= end_ms:
            break
        last_ts = new_end
        cur_start = new_end + 1
    if not all_rows:
        return None
    df = pd.DataFrame(all_rows)
    df['time'] = pd.to_datetime(df['time'], unit='ms', utc=True)
    df['fundingRate'] = df['fundingRate'].astype(float)
    return df.drop_duplicates('time')[['time', 'fundingRate']].set_index('time').sort_index()


def fetch_current_funding(coins=None):
    """
    현재 펀딩레이트 조회 (metaAndAssetCtxs).

    Returns:
        {coin: {'funding_1h': float, 'annual_pct': float}}.
    """
    coins = coins or COINS

    def _f():
        data = _post({'type': 'metaAndAssetCtxs'})
        if not data or len(data) < 2:
            return {}
        universe = data[0]['universe']
        ctxs = data[1]
        name_to_idx = {u['name']: i for i, u in enumerate(universe)}
        out = {}
        for c in coins:
            i = name_to_idx.get(c)
            if i is None or i >= len(ctxs):
                continue
            fr = float(ctxs[i].get('funding', 0))  # 1시간 요율
            out[c] = {'funding_1h': fr, 'annual_pct': round(fr * 24 * 365 * 100, 2)}
        return out

    return _live_cached(('funding', tuple(coins)), _LIVE_TTL, _f)


def fetch_asset_meta(coins=None):
    """
    HL meta로 자산별 최대 레버리지 조회 → 유지증거금률(mmr) 산출.
    mmr ≈ 1 / (2 × maxLeverage)  (HL 근사).

    Returns:
        {coin: {'max_leverage': int, 'mmr': float}}.
    """
    data = _post({'type': 'meta'})
    if not data or 'universe' not in data:
        return {}
    out = {}
    want = set(coins) if coins else None
    for u in data['universe']:
        name = u.get('name')
        if want and name not in want:
            continue
        mx = int(u.get('maxLeverage', 1) or 1)
        out[name] = {'max_leverage': mx, 'mmr': round(1 / (2 * mx), 5)}
    return out


def liquidation_price(entry, leverage, side, mmr):
    """
    HL isolated 청산가 근사.
      롱: liq = entry × (1 − 1/lev + mmr)
      숏: liq = entry × (1 + 1/lev − mmr)
    side: 'long' | 'short'. entry/leverage>0 가정.
    """
    if entry <= 0 or leverage <= 0:
        return None
    if side == 'long':
        return entry * (1 - 1 / leverage + mmr)
    return entry * (1 + 1 / leverage - mmr)


def relative_series(coin_a, coin_b, days=180, interval='1d'):
    """
    두 자산 상대가격(A/B) 시계열.

    Returns:
        list[{'time': int(sec), 'value': float}], 실패 시 [].
    """
    da = fetch_candles(coin_a, days=days, interval=interval)
    db = fetch_candles(coin_b, days=days, interval=interval)
    if da is None or db is None:
        return []
    ratio = (da['close'] / db['close']).dropna()
    return [{'time': int(ts.timestamp()), 'value': round(float(v), 6)}
            for ts, v in ratio.items()]
