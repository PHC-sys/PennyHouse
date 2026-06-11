"""
Hyperliquid 전 자산 레지스트리 (Crypto + TradFi + Pre-IPO).

- 메인 perp dex: 크립토 (BTC, ETH, ...)
- HIP-3 빌더 dex:
    xyz  → TradFi (미국주식/원자재/FX/지수)
    vntl → Pre-IPO + 테마 바스켓 (OPENAI/ANTHROPIC/SPACEX/MAG7 ...)
자산명은 HIP-3의 경우 prefix 포함: 'xyz:NVDA', 'vntl:OPENAI'.
"""
import time
import requests
import numpy as np

from .prices import HL_API, _post, fetch_candles

# 다룰 dex 소스 (메인=None) → 대분류
DEX_SOURCES = [
    (None,   'crypto'),
    ('xyz',  'tradfi'),
    ('vntl', 'preipo'),
]

# TradFi(xyz) 세부 분류용 키워드
_COMMODITIES = {'GOLD', 'SILVER', 'PLATINUM', 'PALLADIUM', 'COPPER', 'ALUMINIUM',
                'BRENTOIL', 'CL', 'NATGAS', 'CORN', 'WHEAT', 'URANIUM', 'URNM',
                'TTF', 'SOY'}
_FX = {'EUR', 'GBP', 'JPY', 'KRW', 'NOK', 'DXY'}
_INDICES = {'SP500', 'XYZ100', 'NIFTY', 'KR200', 'JP225', 'IBOV', 'VIX', 'VOL',
            'EWY', 'EWZ', 'EWJ', 'EWT', 'XLE', 'USTECH', 'US500', 'USA100', 'USA500'}

_CACHE = {}
_TTL = 120  # 2분


def _subcategory(dex, raw_name):
    """xyz(tradfi) 내 세부 분류."""
    if dex != 'xyz':
        return None
    n = raw_name.upper()
    if n in _COMMODITIES:
        return 'commodity'
    if n in _FX:
        return 'fx'
    if n in _INDICES:
        return 'index'
    return 'stock'


def fetch_universe(use_cache=True):
    """
    전 자산 레지스트리 (라이브 mark/funding/24h 변화 포함).

    Returns:
        list[{symbol, display, category, sub, dex, max_leverage,
              price, funding_annual, change_24h}]
    """
    if use_cache and 'uni' in _CACHE and time.time() - _CACHE['uni'][0] < _TTL:
        return _CACHE['uni'][1]

    out = []
    for dex, category in DEX_SOURCES:
        payload = {'type': 'metaAndAssetCtxs'}
        if dex:
            payload['dex'] = dex
        data = _post(payload)
        if not isinstance(data, list) or len(data) < 2:
            continue
        universe, ctxs = data[0]['universe'], data[1]
        for i, u in enumerate(universe):
            if u.get('isDelisted'):
                continue
            raw = u['name']
            symbol = raw if dex is None else raw  # 이미 prefix 포함됨
            disp = raw.split(':')[-1]
            ctx = ctxs[i] if i < len(ctxs) else {}
            mark = float(ctx.get('markPx') or 0)
            prev = float(ctx.get('prevDayPx') or 0)
            funding_1h = float(ctx.get('funding') or 0)
            change = round((mark / prev - 1) * 100, 2) if prev > 0 else None
            volume = float(ctx.get('dayNtlVlm') or 0)          # 24h 명목 거래량($)
            oi = float(ctx.get('openInterest') or 0) * mark    # 미결제약정($ 환산)
            out.append({
                'symbol': symbol,
                'display': disp,
                'category': category,
                'sub': _subcategory(dex, disp),
                'dex': dex,
                'max_leverage': int(u.get('maxLeverage', 1) or 1),
                'price': mark,
                'funding_1h': funding_1h,
                'funding_annual': round(funding_1h * 24 * 365 * 100, 2),
                'change_24h': change,
                'volume_24h': round(volume),
                'open_interest': round(oi),
            })
    _CACHE['uni'] = (time.time(), out)
    return out


def compute_volatility(symbol, days=30):
    """캔들로 일간 변동성(표준편차) 자동 계산. 실패 시 None."""
    df = fetch_candles(symbol, days=days, interval='1d')
    if df is None or len(df) < 5:
        return None
    rets = df['close'].pct_change().dropna()
    return round(float(rets.std()), 4)


def asset_sparkline(symbol, days=30):
    """미니 차트용 종가 시계열. → list[{time, value}]."""
    df = fetch_candles(symbol, days=days, interval='1d')
    if df is None:
        return []
    return [{'time': int(ts.timestamp()), 'value': round(float(v), 4)}
            for ts, v in df['close'].items()]
