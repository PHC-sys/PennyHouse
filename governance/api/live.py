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
LIVE_UPDATED = 0.0    # 마지막 갱신 시각
_lock = threading.Lock()
_started = False


def _on_open(ws):
    for dex in DEXES:
        sub = {'type': 'allMids'}
        if dex:
            sub['dex'] = dex
        ws.send(json.dumps({'method': 'subscribe', 'subscription': sub}))


def _on_message(ws, message):
    global LIVE_UPDATED
    try:
        d = json.loads(message)
    except Exception:
        return
    if d.get('channel') != 'allMids':
        return
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
