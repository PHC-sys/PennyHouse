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

from concurrent.futures import ThreadPoolExecutor
from .prices import HL_API, _post, fetch_candles

# 전 dex → 대분류 (중복 자산은 거래량 큰 dex로 통합)
DEX_CATEGORY = {
    None: 'crypto', 'hyna': 'crypto', 'para': 'crypto',
    'xyz': 'tradfi', 'flx': 'tradfi', 'km': 'tradfi', 'cash': 'tradfi',
    'vntl': 'preipo',
}

# TradFi 세부 분류 키워드 (전 dex 자산 대응, 촘촘하게)
_COMMODITIES = {
    'GOLD', 'SILVER', 'PLATINUM', 'PALLADIUM', 'COPPER', 'ALUMINIUM',
    'OIL', 'WTI', 'WTIOIL', 'USOIL', 'BRENTOIL', 'CL', 'GAS', 'NATGAS',
    'CORN', 'WHEAT', 'SOY', 'URANIUM', 'URNM', 'TTF', 'GLDMINE', 'USENERGY',
    'GOLDJM', 'SILVERJM',
}
_FX = {'EUR', 'GBP', 'JPY', 'KRW', 'NOK', 'DXY'}  # USDE는 합성달러라 제외
_INDICES = {
    'SP500', 'US500', 'USA500', 'USA100', 'USTECH', 'USBOND', 'SMALL2000',
    'XYZ100', 'NIFTY', 'KR200', 'JP225', 'IBOV', 'VIX', 'VOL', 'KWEB',
    'EWY', 'EWZ', 'EWJ', 'EWT', 'XLE',
    # vntl 테마 바스켓 = 섹터 지수
    'MAG7', 'SEMIS', 'DEFENSE', 'NUCLEAR', 'ROBOT', 'INFOTECH', 'BIOTECH', 'ENERGY',
}  # BTCD/TOTAL2/OTHERS(크립토 지수)는 crypto로 둠
# 실제 Pre-IPO/비상장 기업만
_PREIPO = {'SPACEX', 'OPENAI', 'ANTHROPIC', 'SPCX', 'QNT'}
# 스테이블/크립토성 (dex 무관하게 crypto로)
_CRYPTO_FORCE = {'USDE', 'USDC', 'USDH', 'USDT', 'DAI', 'PURRDAT'}

_CACHE = {}
_TTL = 300  # 5분 (라이브 가격은 별도 워커, 레지스트리는 자주 안 변함)
_TOKEN_MAP = {}  # 토큰 인덱스 → 이름 (USDC/USDH...)


def _token_name(idx):
    """결제통화 인덱스 → 이름 (spotMeta 캐시)."""
    if not _TOKEN_MAP:
        sm = _post({'type': 'spotMeta'})
        if sm and 'tokens' in sm:
            for t in sm['tokens']:
                _TOKEN_MAP[t['index']] = t['name']
    return _TOKEN_MAP.get(idx, 'USDC')


def _classify(dex, display):
    """
    자산 분류 — 키워드 우선, dex 폴백.
    (vntl처럼 한 dex에 Pre-IPO+원자재가 섞인 경우 키워드로 정확히 분류)
    Returns: (category, sub)
    """
    n = display.upper()
    if n in _CRYPTO_FORCE:
        return 'crypto', None
    if n in _PREIPO:
        return 'preipo', None
    if n in _COMMODITIES:
        return 'tradfi', 'commodity'
    if n in _FX:
        return 'tradfi', 'fx'
    if n in _INDICES:
        return 'tradfi', 'index'
    # 키워드 미매치 → dex 기준
    if dex in ('xyz', 'flx', 'km', 'cash'):
        return 'tradfi', 'stock'
    if dex == 'vntl':
        return 'preipo', None
    return 'crypto', None  # main, hyna, para 등


def fetch_universe(use_cache=True):
    """
    전 자산 레지스트리 (라이브 mark/funding/24h 변화 포함).

    Returns:
        list[{symbol, display, category, sub, dex, max_leverage,
              price, funding_annual, change_24h}]
    """
    if use_cache and 'uni' in _CACHE and time.time() - _CACHE['uni'][0] < _TTL:
        return _CACHE['uni'][1]

    rows = []
    # 전 dex 수집 (perpDexs로 동적 발견 + 메인) — 병렬 호출로 로딩 단축
    dexs = _post({'type': 'perpDexs'}) or []
    dex_names = [None] + [d['name'] for d in dexs if d and isinstance(d, dict)]

    def _fetch_dex(dex):
        payload = {'type': 'metaAndAssetCtxs'}
        if dex:
            payload['dex'] = dex
        return dex, _post(payload)

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_fetch_dex, dex_names))

    for dex, data in results:
        if not isinstance(data, list) or len(data) < 2:
            continue
        universe, ctxs = data[0]['universe'], data[1]
        quote = _token_name(data[0].get('collateralToken', 0))
        for i, u in enumerate(universe):
            if u.get('isDelisted'):
                continue
            raw = u['name']
            disp = raw.split(':')[-1]
            category, sub = _classify(dex, disp)
            ctx = ctxs[i] if i < len(ctxs) else {}
            mark = float(ctx.get('markPx') or 0)
            prev = float(ctx.get('prevDayPx') or 0)
            funding_1h = float(ctx.get('funding') or 0)
            change = round((mark / prev - 1) * 100, 2) if prev > 0 else None
            volume = float(ctx.get('dayNtlVlm') or 0)
            oi = float(ctx.get('openInterest') or 0) * mark
            rows.append({
                'symbol': raw, 'display': disp,
                'category': category, 'sub': sub,
                'dex': dex or 'main',
                'max_leverage': int(u.get('maxLeverage', 1) or 1),
                'quote': quote, 'price': mark, 'funding_1h': funding_1h,
                'funding_annual': round(funding_1h * 24 * 365 * 100, 2),
                'change_24h': change,
                'volume_24h': round(volume), 'open_interest': round(oi),
            })

    # 중복 자산(같은 display)은 거래량 큰 dex만 대표로 (순수 거래량 기준)
    best = {}
    for r in rows:
        key = r['display']
        if key not in best or r['volume_24h'] > best[key]['volume_24h']:
            best[key] = r
    out = list(best.values())
    out.sort(key=lambda r: -r['volume_24h'])
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


_SPARK_CACHE = {}
_SPARK_TTL = 300


def batch_sparklines(symbols, days=14):
    """
    여러 심볼 스파크라인을 제한된 동시성으로 한 번에 수집 (마켓 타일용).
    개별 호출 폭탄 방지 → 로딩 안정화.

    Returns: {symbol: [{time, value}, ...]}
    """
    out, todo = {}, []
    now = time.time()
    for s in symbols:
        c = _SPARK_CACHE.get((s, days))
        if c and now - c[0] < _SPARK_TTL:
            out[s] = c[1]
        else:
            todo.append(s)

    def _one(s):
        return s, asset_sparkline(s, days=days)

    if todo:
        # _post 자체가 세마포어(8)로 제한되므로 워커는 넉넉히
        with ThreadPoolExecutor(max_workers=12) as ex:
            for s, series in ex.map(_one, todo):
                _SPARK_CACHE[(s, days)] = (now, series)
                out[s] = series
    return out
