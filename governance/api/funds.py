# -*- coding: utf-8 -*-
"""
펀드별 페이퍼 운용 엔진 (멀티펀드).

각 펀드는 자기 유니버스/프로파일로 독립 운용.
- 투표/NAV는 SQLite 영속화(store)
- 실시간 평가는 라이브 워커 메모리(live) 사용 (REST 호출 X)
- 비중/손익/평단 등 런타임 상태는 메모리 캐시 (없으면 votes로 재구성)
"""
import time
import threading

from governance.engine import (
    FUND_PROFILES, adaptive_alpha, simulate_votes, votes_to_target,
    liquidation_price, compute_volatility, fetch_universe,
)
from governance.engine.voting import apply_ema
from governance.api import store, live

_INITIAL = 100_000.0
_lock = threading.Lock()
_runtime = {}      # fund_id -> {weights, equity, asset_pnl, avg_entry, last_prices, last_target}
_vol_cache = {}    # symbol -> (ts, vol)
_VOL_TTL = 1800


def _vol(symbol):
    c = _vol_cache.get(symbol)
    if c and time.time() - c[0] < _VOL_TTL:
        return c[1]
    v = compute_volatility(symbol) or 0.05
    _vol_cache[symbol] = (time.time(), v)
    return v


def _fresh_runtime(fund):
    uni = fund['universe']
    init = fund.get('initial_deposit') or _INITIAL
    iw = fund.get('init_weights') or {}
    if iw:
        weights = {c: float(iw.get(c, 0)) for c in uni}
    else:
        weights = {c: 100.0 / len(uni) for c in uni}  # 균등 롱
    return {
        'weights': weights, 'equity': init,
        'asset_pnl': {c: 0.0 for c in uni},
        'avg_entry': {c: None for c in uni},
        'last_prices': {}, 'last_target': None, 'initial': init,
    }


def _rt(fund):
    """펀드 런타임 상태 (없으면 생성 + 기존 투표 반영)."""
    fid = fund['id']
    if fid not in _runtime:
        _runtime[fid] = _fresh_runtime(fund)
        _aggregate(fund)  # 저장된 투표로 목표 비중 1회 반영
    return _runtime[fid]


def _aggregate(fund):
    """저장된 투표 → 목표 비중 + EMA 한 스텝."""
    fid = fund['id']
    rt = _runtime[fid]
    uni = fund['universe']
    votes = store.get_votes(fid)
    if not votes:
        return
    profile = FUND_PROFILES[fund['profile']]
    vr = simulate_votes(votes, uni)
    vol_map = {c: _vol(c) for c in uni}
    target = votes_to_target(vr, uni, vol_map)
    rt['last_target'] = target
    if target is None:
        return
    alpha = adaptive_alpha(7, profile['T_CONVERGE'])
    cap = profile['MAX_WEIGHT']
    rt['weights'] = apply_ema(rt['weights'], target, alpha, cap, uni)
    # 평균단가 갱신 (현재 라이브가 기준)
    prices = live.get_mids(uni)
    for c in uni:
        px = prices.get(c)
        w = rt['weights'][c]
        if px and (rt['avg_entry'][c] is None or abs(w) > 1e-9):
            if rt['avg_entry'][c] is None:
                rt['avg_entry'][c] = px


def _leverage(fund):
    if fund.get('leverage'):
        return fund['leverage']
    return FUND_PROFILES[fund['profile']]['FUND_LEVERAGE']


def _mark_to_market(fund):
    """라이브 가격으로 평가 → equity + 코인별 손익."""
    fid = fund['id']
    rt = _runtime[fid]
    uni = fund['universe']
    prices = live.get_mids(uni)
    if not prices:
        return
    last = rt['last_prices']
    lev = _leverage(fund)
    if last:
        eq = rt['equity']
        total = 0.0
        for c in uni:
            if c in prices and c in last and last[c] > 0:
                ret = prices[c] / last[c] - 1
                pnl = (rt['weights'][c] / 100) * eq * lev * ret
                rt['asset_pnl'][c] += pnl
                total += pnl
        rt['equity'] = max(eq + total, 0)
    rt['last_prices'] = dict(prices)
    for c in uni:
        if rt['avg_entry'][c] is None and abs(rt['weights'][c]) > 1e-9 and c in prices:
            rt['avg_entry'][c] = prices[c]


def submit_vote(fund, user, deposit, votes):
    uni = fund['universe']
    votes = {c: int(votes.get(c, 0)) for c in uni}
    with _lock:
        store.upsert_vote(fund['id'], user, float(deposit), votes)
        _rt(fund)
        _aggregate(fund)
        _mark_to_market(fund)
        _snapshot_nav(fund)


def _snapshot_nav(fund):
    rt = _runtime[fund['id']]
    eq = rt['equity']
    store.append_nav(fund['id'], int(time.time()), round(eq, 2),
                     round((eq / rt['initial'] - 1) * 100, 3))


def get_state(fund):
    with _lock:
        rt = _rt(fund)
        _mark_to_market(fund)
        uni = fund['universe']
        eq = rt['equity']
        lev = _leverage(fund)
        prices = rt['last_prices']
        # 레지스트리에서 펀딩/레버리지 (HIP-3 포함 전 자산 커버)
        reg = {a['symbol']: a for a in fetch_universe()}
        meta = {}
        for c in uni:
            mx = reg.get(c, {}).get('max_leverage', 1) or 1
            meta[c] = {'max_leverage': mx, 'mmr': round(1 / (2 * mx), 5)}

        votes = store.get_votes(fund['id'])
        total_dep = sum(v['deposit'] for v in votes) or 0
        participants = []
        for v in votes:
            share = v['deposit'] / total_dep if total_dep else 0
            participants.append({
                'user': v['user'], 'deposit': v['deposit'],
                'share_pct': round(share * 100, 1), 'votes': v['votes'],
                'paper_value': round(eq * share, 2),
                'ret_pct': round((eq / rt['initial'] - 1) * 100, 2),
            })
        participants.sort(key=lambda x: x['paper_value'], reverse=True)

        carry_annual = 0.0
        assets = {}
        for c in uni:
            w = rt['weights'][c]
            ann = reg.get(c, {}).get('funding_annual', 0)
            contrib = -(w / 100) * lev * ann
            carry_annual += contrib
            entry = rt['avg_entry'][c]
            side = 'long' if w >= 0 else 'short'
            mmr = meta.get(c, {}).get('mmr', 0.02)
            liq = (liquidation_price(entry, lev, side, mmr)
                   if entry and abs(w) > 1e-9 and lev > 1 else None)
            px = prices.get(c)
            liq_dist = round(abs(px - liq) / px * 100, 1) if liq and px else None
            assets[c] = {
                'weight': round(w, 1),
                'return_pct': round(rt['asset_pnl'][c] / rt['initial'] * 100, 2),
                'funding_carry': round(contrib, 2),
                'avg_entry': round(entry, 4) if entry else None,
                'price': px, 'liq_price': round(liq, 4) if liq else None,
                'liq_dist_pct': liq_dist,
                'max_leverage': meta.get(c, {}).get('max_leverage'),
            }

        nav = store.get_nav(fund['id'], limit=300)
        return {
            'fund': {k: fund[k] for k in ('id', 'name', 'kind', 'visibility',
                                          'profile', 'universe')},
            'leverage': lev, 'fund_equity': round(eq, 2),
            'fund_return_pct': round((eq / rt['initial'] - 1) * 100, 2),
            'funding_carry_annual_pct': round(carry_annual, 2),
            'weights': {c: round(rt['weights'][c], 1) for c in uni},
            'target': (None if rt['last_target'] is None
                       else {c: round(rt['last_target'][c], 1) for c in uni}),
            'assets': assets, 'participants': participants,
            'nav_history': nav, 'prices': prices,
        }


def reset_fund(fund):
    """펀드 운용 상태 초기화 (투표/NAV 삭제, 메타 유지)."""
    with _lock:
        fid = fund['id']
        # votes/nav 비우기
        import governance.api.store as st
        with st._lock, st._conn() as c:
            c.execute("DELETE FROM votes WHERE fund_id=?", (fid,))
            c.execute("DELETE FROM nav_history WHERE fund_id=?", (fid,))
        _runtime.pop(fid, None)
