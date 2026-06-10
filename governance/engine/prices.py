"""Hyperliquid 가격/캔들 데이터 수집."""

import time
import requests
import pandas as pd
from datetime import datetime, timezone

from .profiles import COINS

HL_API = 'https://api.hyperliquid.xyz/info'

# 간단한 인메모리 캐시 (코인+interval+days → (timestamp, df))
_CACHE = {}
_CACHE_TTL = 300  # 5분


def fetch_candles(coin, days=180, interval='1d', use_cache=True):
    """
    HL candleSnapshot API로 OHLCV 수집.

    Returns:
        pd.DataFrame[open,high,low,close,volume] (UTC 인덱스), 실패 시 None.
    """
    key = (coin, interval, days)
    if use_cache and key in _CACHE:
        ts, df = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return df.copy()

    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 86400 * 1000
    try:
        res = requests.post(HL_API, json={
            'type': 'candleSnapshot',
            'req': {'coin': coin, 'interval': interval,
                    'startTime': start_ms, 'endTime': end_ms}
        }, timeout=15)
        rows = res.json()
    except Exception:
        return None
    if not rows:
        return None

    df = pd.DataFrame(rows)
    df['time'] = pd.to_datetime(df['t'], unit='ms', utc=True)
    df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low',
                            'c': 'close', 'v': 'volume'})
    df = df[['time', 'open', 'high', 'low', 'close', 'volume']].set_index('time')
    df = df.astype(float).sort_index()

    _CACHE[key] = (time.time(), df.copy())
    return df


def fetch_closes(coins=None, days=180, interval='1d'):
    """
    여러 코인의 종가를 공통 날짜로 정렬한 DataFrame + 일간수익률 반환.

    Returns:
        (closes_df, returns_df). 데이터 없으면 (None, None).
    """
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


def fetch_current_prices(coins=None):
    """
    HL allMids로 현재가 조회.

    Returns:
        {coin: float} 현재가. 실패 시 {}.
    """
    coins = coins or COINS
    try:
        res = requests.post(HL_API, json={'type': 'allMids'}, timeout=15)
        mids = res.json()
    except Exception:
        return {}
    return {c: float(mids[c]) for c in coins if c in mids}
