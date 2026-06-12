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

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None

WS_URL = 'wss://api.hyperliquid.xyz/ws'
DEXES = [None, 'xyz', 'vntl']  # 메인 + HIP-3

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
    for dex in DEXES:
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
