# -*- coding: utf-8 -*-
"""
라이브 가격 수집 워커 + 메모리 스토어.

HL WebSocket(allMids, main+xyz+vntl dex)을 단일 백그라운드 스레드로 구독해
메모리 딕셔너리를 갱신한다. 브라우저는 이 메모리만 읽으므로 HL 호출이
워커 1곳으로 집중된다 (Fan-out, 가벼움).
"""
import json
import time
import threading

import requests

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None

WS_URL = 'wss://api.hyperliquid.xyz/ws'
HL_INFO = 'https://api.hyperliquid.xyz/info'

# 구독할 dex 목록 — perpDexs로 동적 발견 (레지스트리 fetch_universe와 일치시킴).
# 정적 3개로 두면 km/flx 등 다른 dex 자산이 라이브 mid를 못 받아
# 평단·청산가·손익이 비는 버그가 생긴다. 발견 실패 시 아래 폴백 사용.
_DEX_FALLBACK = [None, 'xyz', 'vntl']
_DEX_LIST = list(_DEX_FALLBACK)


def _refresh_dexes():
    """HL perpDexs로 전체 dex 목록 갱신 (재접속마다 호출, 새 dex 자동 반영)."""
    global _DEX_LIST
    try:
        r = requests.post(HL_INFO, json={'type': 'perpDexs'}, timeout=10)
        dexs = r.json() or []
        names = [None] + [d['name'] for d in dexs if d and isinstance(d, dict)]
        if names:
            _DEX_LIST = names
    except Exception:
        pass  # 폴백(기존 값) 유지

# 메모리 스토어 (스레드 안전: 단순 dict 대입)
LIVE_MIDS = {}        # symbol -> float price
LIVE_CTX = {}         # symbol -> {funding, markPx, openInterest, dayNtlVlm, prevDayPx, ...}
LIVE_UPDATED = 0.0    # 마지막 갱신 시각
_lock = threading.Lock()
_started = False

# 자산별 activeAssetCtx 구독 (보는 자산만 — refcount 공유)
_ctx_refs = {}        # symbol -> 구독 클라이언트 수
_ws_ref = [None]      # 현재 WebSocketApp (다른 스레드에서 subscribe 전송용)


def _send(obj):
    ws = _ws_ref[0]
    if ws is not None:
        try:
            ws.send(json.dumps(obj))
            return True
        except Exception:
            return False
    return False


def _on_open(ws):
    _ws_ref[0] = ws
    for dex in _DEX_LIST:
        sub = {'type': 'allMids'}
        if dex:
            sub['dex'] = dex
        ws.send(json.dumps({'method': 'subscribe', 'subscription': sub}))
    # 재접속 시 활성 ctx 자산 재구독
    with _lock:
        active = list(_ctx_refs.keys())
    for coin in active:
        ws.send(json.dumps({'method': 'subscribe',
                            'subscription': {'type': 'activeAssetCtx', 'coin': coin}}))


def _on_message(ws, message):
    global LIVE_UPDATED
    try:
        d = json.loads(message)
    except Exception:
        return
    ch = d.get('channel')
    if ch == 'allMids':
        mids = d.get('data', {}).get('mids', {})
        updates = {}
        for k, v in mids.items():
            if k.startswith('@') or k.startswith('#'):  # 스팟 인덱스 페어 제외
                continue
            try:
                updates[k] = float(v)
            except (TypeError, ValueError):
                continue
        if updates:
            with _lock:
                LIVE_MIDS.update(updates)
                LIVE_UPDATED = time.time()
    elif ch == 'activeAssetCtx':
        data = d.get('data', {})
        coin = data.get('coin')
        ctx = data.get('ctx')
        if coin and ctx:
            with _lock:
                LIVE_CTX[coin] = ctx


def _run():
    """연결 끊기면 재접속 (지수 백오프)."""
    backoff = 1
    while True:
        try:
            _refresh_dexes()  # 접속 전 dex 목록 최신화 (새 dex 자동 구독)
            ws = websocket.WebSocketApp(
                WS_URL, on_open=_on_open, on_message=_on_message)
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception:
            pass
        time.sleep(min(backoff, 30))
        backoff = min(backoff * 2, 30)


def start_worker():
    """FastAPI 시작 시 1회 호출. 데몬 스레드로 워커 기동."""
    global _started
    if _started or websocket is None:
        return
    _started = True
    threading.Thread(target=_run, daemon=True, name='hl-live-worker').start()


def get_mids(symbols=None):
    """현재 라이브 가격 스냅샷. symbols 주면 해당만."""
    with _lock:
        if symbols:
            return {s: LIVE_MIDS[s] for s in symbols if s in LIVE_MIDS}
        return dict(LIVE_MIDS)


def get_price(symbol):
    with _lock:
        return LIVE_MIDS.get(symbol)


def get_marks(symbols=None):
    """
    마크가(markPx) 스냅샷 — 포지션 시가평가용 (HL도 손익/청산을 markPx로 계산).
    activeAssetCtx 구독이 있으면 그 markPx, 없으면 allMids mid로 폴백.
    HIP-3(TradFi·Pre-IPO) 저유동성 자산은 mid가 mark와 벌어져 mid로 마킹하면
    손익이 안 움직임 → mark 우선이 정답.
    """
    with _lock:
        syms = list(symbols) if symbols else list(LIVE_MIDS.keys())
        out = {}
        for s in syms:
            c = LIVE_CTX.get(s)
            if c and c.get('markPx'):
                try:
                    out[s] = float(c['markPx'])
                    continue
                except (TypeError, ValueError):
                    pass
            if s in LIVE_MIDS:
                out[s] = LIVE_MIDS[s]
        return out


def ensure_ctx(symbols):
    """펀드 보유 자산의 markPx가 흐르도록 activeAssetCtx 구독 보장(멱등).
    이미 구독된 심볼은 건너뜀(refcount 미증가). 워커 재접속 시 _on_open이 재구독."""
    new = []
    with _lock:
        for s in symbols:
            if s not in _ctx_refs:
                _ctx_refs[s] = 1
                new.append(s)
    for s in new:
        _send({'method': 'subscribe',
               'subscription': {'type': 'activeAssetCtx', 'coin': s}})


def status():
    with _lock:
        return {'count': len(LIVE_MIDS), 'updated': LIVE_UPDATED,
                'age_sec': round(time.time() - LIVE_UPDATED, 1) if LIVE_UPDATED else None,
                'connected': websocket is not None}


# ── activeAssetCtx: 보는 자산만 구독 (refcount 공유) ───────────────
def subscribe_ctx(coin):
    """자산 ctx 구독 시작 (첫 구독자면 HL에 subscribe 전송)."""
    with _lock:
        first = coin not in _ctx_refs or _ctx_refs[coin] <= 0
        _ctx_refs[coin] = _ctx_refs.get(coin, 0) + 1
    if first:
        _send({'method': 'subscribe',
               'subscription': {'type': 'activeAssetCtx', 'coin': coin}})


def unsubscribe_ctx(coin):
    """구독 해제 (마지막 구독자면 HL에 unsubscribe)."""
    with _lock:
        n = _ctx_refs.get(coin, 0) - 1
        if n <= 0:
            _ctx_refs.pop(coin, None)
            last = True
        else:
            _ctx_refs[coin] = n
            last = False
    if last:
        _send({'method': 'unsubscribe',
               'subscription': {'type': 'activeAssetCtx', 'coin': coin}})
        with _lock:
            LIVE_CTX.pop(coin, None)


def get_ctx(coin):
    """자산 라이브 ctx (펀딩 연환산·24h변동·거래량·OI 가공 포함)."""
    with _lock:
        c = LIVE_CTX.get(coin)
    if not c:
        return None
    try:
        mark = float(c.get('markPx') or 0)
        prev = float(c.get('prevDayPx') or 0)
        fr = float(c.get('funding') or 0)
        oi = float(c.get('openInterest') or 0) * mark
        vol = float(c.get('dayNtlVlm') or 0)
        return {
            'price': mark,
            'funding_annual': round(fr * 24 * 365 * 100, 2),
            'change_24h': round((mark / prev - 1) * 100, 2) if prev > 0 else None,
            'open_interest': round(oi),
            'volume_24h': round(vol),
        }
    except (TypeError, ValueError):
        return None
