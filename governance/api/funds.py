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
    liquidation_price, compute_volatility, fetch_universe, delisted_map,
)
from governance.engine.voting import apply_ema
from governance.api import store, live

_INITIAL = 100_000.0
_lock = threading.Lock()


def _retpct(eq, init, nd=2):
    """수익률(%) — 자본 0(전원 회수)일 때 0 나눗셈 방지."""
    return round((eq / init - 1) * 100, nd) if init and init > 1e-9 else 0.0


def _pnlpct(pnl, init):
    """자산 손익 기여도(%) — 자본 0일 때 0 나눗셈 방지."""
    return round(pnl / init * 100, 2) if init and init > 1e-9 else 0.0


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
        'settled': {},  # 상장폐지로 정산된 자산: symbol -> {final_price, ts, successor}
    }


def _reconcile_delisted(fund, rt):
    """
    펀드가 담은 자산이 상장폐지되면 settle-to-cash: 그 leg를 마지막 mark로 청산.
    → 비중 0(빠진 만큼 현금), 손익(asset_pnl)은 그 시점 값으로 동결, settled 기록.
    HL이 진실의 원천이므로 재시작해도 delisted_map으로 다시 복원된다.
    (실제 HL이 perp을 delist할 때 미결제 포지션을 최종 mark로 강제정산하는 것과 동일)
    """
    dl = delisted_map()
    if not dl:
        return
    for c in fund['universe']:
        if c in dl and c not in rt['settled']:
            info = dl[c]
            rt['settled'][c] = {
                'final_price': info.get('final_price'),
                'ts': int(time.time()),
                'successor': info.get('successor'),
            }
            rt['weights'][c] = 0.0  # 포지션 청산 → 빠진 비중은 현금으로 흡수


def _active(fund, rt):
    """정산되지 않은(운용 중) 자산만."""
    return [c for c in fund['universe'] if c not in rt['settled']]


_RT_KEYS = ('weights', 'equity', 'asset_pnl', 'avg_entry', 'last_prices',
            'last_target', 'initial', 'settled', 'target_cash')
_last_save = {}     # fund_id -> 마지막 스냅샷 저장 시각 (쓰기 쓰로틀)
_SAVE_EVERY = 8.0   # 초


def _restore_runtime(fund, snap):
    """저장된 스냅샷 → 런타임 dict (유니버스 키 보강)."""
    rt = _fresh_runtime(fund)
    for k in _RT_KEYS:
        if k in snap:
            rt[k] = snap[k]
    rt.setdefault('settled', {})
    uni = fund['universe']
    for c in uni:  # 유니버스 키 누락 방지 (방어적)
        rt['weights'].setdefault(c, 0.0)
        rt['asset_pnl'].setdefault(c, 0.0)
        rt['avg_entry'].setdefault(c, None)
    return rt


def _save_runtime(fund, force=False):
    """런타임 스냅샷 영속화 (쓰로틀). 재시작 시 라이브 평가 이어짐."""
    fid = fund['id']
    now = time.time()
    if not force and now - _last_save.get(fid, 0) < _SAVE_EVERY:
        return
    _last_save[fid] = now
    rt = _runtime[fid]
    store.save_runtime(fid, {k: rt.get(k) for k in _RT_KEYS})


def _rt(fund):
    """펀드 런타임 상태 (없으면 스냅샷 복원 → 없으면 생성 + 기존 투표 반영)."""
    fid = fund['id']
    if fid not in _runtime:
        snap = store.load_runtime(fid)
        if snap:
            _runtime[fid] = _restore_runtime(fund, snap)
            _reconcile_delisted(fund, _runtime[fid])  # 다운된 새 상장폐지 반영
        else:
            _runtime[fid] = _fresh_runtime(fund)
            _reconcile_delisted(fund, _runtime[fid])
            _aggregate(fund)  # 저장된 투표로 목표 비중 1회 반영
    return _runtime[fid]


def _aggregate(fund):
    """저장된 투표 → 목표 비중 + EMA 한 스텝."""
    fid = fund['id']
    rt = _runtime[fid]
    uni = _active(fund, rt)  # 정산(상장폐지) 자산은 집계 제외 → 비중 0 유지
    votes = store.get_votes(fid)
    if not votes:
        return
    profile = FUND_PROFILES[fund['profile']]
    # 현금 보유 비율 = 참여자 cash 투표의 예치금 가중평균 (0~100)
    total_dep = sum(v['deposit'] for v in votes) or 1
    cash_pct = sum(v['deposit'] * float(v['votes'].get('_cash', 0)) for v in votes) / total_dep
    cash_pct = max(0.0, min(100.0, cash_pct))
    rt['target_cash'] = cash_pct

    vr = simulate_votes(votes, uni)
    vol_map = {c: _vol(c) for c in uni}
    target = votes_to_target(vr, uni, vol_map)
    if target is not None:
        # 종목 비중은 (100-cash)로 스케일 → 나머지는 현금
        scale = (100.0 - cash_pct) / 100.0
        target = {c: target[c] * scale for c in uni}
    rt['last_target'] = target
    if target is None:
        return
    alpha = adaptive_alpha(7, profile['T_CONVERGE'])
    cap = profile['MAX_WEIGHT']
    rt['weights'] = apply_ema(rt['weights'], target, alpha, cap, uni)
    # apply_ema는 active uni만 키로 반환 → 정산 자산 키(비중 0)를 복원해 둠
    for c in rt['settled']:
        rt['weights'].setdefault(c, 0.0)
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


_reg_cache = {'ts': 0, 'data': {}}


def _registry():
    """자산 레지스트리 맵 (60초 캐시)."""
    if time.time() - _reg_cache['ts'] > 60:
        _reg_cache['data'] = {a['symbol']: a for a in fetch_universe()}
        _reg_cache['ts'] = time.time()
    return _reg_cache['data']


def _eff_lev(fund_lev, symbol, reg):
    """자산별 유효 레버리지 = min(펀드 레버리지, 자산 최대 레버리지)."""
    amax = reg.get(symbol, {}).get('max_leverage') or fund_lev
    return min(fund_lev, amax)


def _mark_to_market(fund):
    """라이브 가격으로 평가 → equity + 코인별 손익."""
    fid = fund['id']
    rt = _runtime[fid]
    _reconcile_delisted(fund, rt)  # 세션 중 새로 상장폐지되면 즉시 정산
    uni = _active(fund, rt)        # 정산 자산은 마킹·손익적립에서 제외(동결)
    prices = live.get_mids(uni)
    if not prices:
        return
    last = rt['last_prices']
    lev = _leverage(fund)
    reg = _registry()
    if last:
        eq = rt['equity']
        total = 0.0
        for c in uni:
            if c in prices and c in last and last[c] > 0:
                ret = prices[c] / last[c] - 1
                elev = _eff_lev(lev, c, reg)  # 자산 한도 캡
                pnl = (rt['weights'][c] / 100) * eq * elev * ret
                rt['asset_pnl'][c] += pnl
                total += pnl
        rt['equity'] = max(eq + total, 0)
    rt['last_prices'] = dict(prices)
    for c in uni:
        if rt['avg_entry'][c] is None and abs(rt['weights'][c]) > 1e-9 and c in prices:
            rt['avg_entry'][c] = prices[c]
    # 분 단위 NAV 기록 (규칙적 시계열, 같은 분 덮어쓰기)
    eq = rt['equity']
    store.upsert_nav_minute(fund['id'], round(eq, 2), _retpct(eq, rt['initial'], 4))
    _save_runtime(fund)  # 런타임 스냅샷 영속(쓰로틀) → 재시작해도 평가 이어짐


def submit_vote(fund, user, deposit, votes):
    uni = fund['universe']
    cash = max(0.0, min(100.0, float(votes.get('cash', 0) or 0)))
    votes = {c: int(votes.get(c, 0)) for c in uni}
    votes['_cash'] = cash  # 현금 보유 비율(투표)
    with _lock:
        store.upsert_vote(fund['id'], user, float(deposit), votes)
        _rt(fund)
        _aggregate(fund)
        _mark_to_market(fund)  # 내부에서 분 단위 NAV 기록
        _save_runtime(fund, force=True)  # 투표 직후 즉시 영속


def _snapshot_nav(fund):
    rt = _runtime[fund['id']]
    eq = rt['equity']
    store.append_nav(fund['id'], int(time.time()), round(eq, 2),
                     _retpct(eq, rt['initial'], 3))


def get_state(fund):
    with _lock:
        rt = _rt(fund)
        _mark_to_market(fund)
        uni = fund['universe']
        eq = rt['equity']
        lev = _leverage(fund)
        prices = rt['last_prices']
        # 레지스트리에서 펀딩/레버리지/결제통화 (HIP-3 포함 전 자산 커버)
        reg = {a['symbol']: a for a in fetch_universe()}

        votes = store.get_votes(fund['id'])
        total_dep = sum(v['deposit'] for v in votes) or 0
        participants = []
        for v in votes:
            share = v['deposit'] / total_dep if total_dep else 0
            participants.append({
                'user': v['user'], 'deposit': v['deposit'],
                'share_pct': round(share * 100, 1), 'votes': v['votes'],
                'paper_value': round(eq * share, 2),
                'ret_pct': _retpct(eq, rt['initial']),
            })
        participants.sort(key=lambda x: x['paper_value'], reverse=True)

        carry_annual = 0.0
        assets = {}
        gross = 0.0
        for c in uni:
            if c in rt['settled']:
                # 상장폐지로 정산된 자산: 동결 행 (비중 0, 손익은 정산 시점값 고정)
                s = rt['settled'][c]
                assets[c] = {
                    'weight': 0.0, 'settled': True,
                    'final_price': (round(s['final_price'], 4)
                                    if s.get('final_price') else None),
                    'successor': s.get('successor'),
                    'return_pct': _pnlpct(rt['asset_pnl'][c], rt['initial']),
                    'funding_carry': 0.0, 'avg_entry': None, 'price': None,
                    'liq_price': None, 'liq_dist_pct': None,
                    'max_leverage': reg.get(c, {}).get('max_leverage') or lev,
                    'eff_leverage': lev,
                    'quote': reg.get(c, {}).get('quote', 'USDC'),
                }
                continue
            w = rt['weights'][c]
            gross += abs(w)
            amax = reg.get(c, {}).get('max_leverage') or lev
            elev = min(lev, amax)                 # 자산 한도 캡
            mmr = 1 / (2 * amax)                  # HL 공식 = 1/(2×maxLev)
            ann = reg.get(c, {}).get('funding_annual', 0)
            contrib = -(w / 100) * elev * ann
            carry_annual += contrib
            entry = rt['avg_entry'][c]
            side = 'long' if w >= 0 else 'short'
            liq = (liquidation_price(entry, elev, side, mmr)
                   if entry and abs(w) > 1e-9 and elev > 1 else None)
            px = prices.get(c)
            liq_dist = round(abs(px - liq) / px * 100, 1) if liq and px else None
            assets[c] = {
                'weight': round(w, 1),
                'return_pct': _pnlpct(rt['asset_pnl'][c], rt['initial']),
                'funding_carry': round(contrib, 2),
                'avg_entry': round(entry, 4) if entry else None,
                'price': px, 'liq_price': round(liq, 4) if liq else None,
                'liq_dist_pct': liq_dist,
                'max_leverage': amax, 'eff_leverage': elev,
                'quote': reg.get(c, {}).get('quote', 'USDC'),
            }

        # 현금: 투표로 정한 목표(target_cash)와 실제 미투입(100-gross) 모두 제공
        cash_pct = round(max(0.0, 100 - gross), 1)
        target_cash = round(rt.get('target_cash', 0.0), 1)

        nav = store.get_nav(fund['id'], limit=300)
        return {
            'fund': {k: fund[k] for k in ('id', 'name', 'kind', 'visibility',
                                          'profile', 'universe')},
            'leverage': lev, 'fund_equity': round(eq, 2),
            'fund_return_pct': _retpct(eq, rt['initial']),
            'funding_carry_annual_pct': round(carry_annual, 2),
            'cash_pct': cash_pct, 'target_cash_pct': target_cash,
            'weights': {c: round(rt['weights'].get(c, 0.0), 1) for c in uni},
            'target': (None if rt['last_target'] is None
                       else {c: round(rt['last_target'].get(c, 0.0), 1) for c in uni}),
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
        store.delete_runtime(fid)  # 스냅샷도 비움 (리셋이 진짜 리셋되게)
        _runtime.pop(fid, None)
        _last_save.pop(fid, None)


def current_equity(fund):
    """현재 평가 자산(런타임). 삭제 가능 여부(자금 0) 판단용."""
    with _lock:
        rt = _rt(fund)
        _mark_to_market(fund)
        return rt['equity']


def redeem(fund, user):
    """
    참가자 지분 회수(출금/탈퇴). 그의 share 비율만큼 펀드 자본을 인출하고
    투표를 삭제한다. (실제 주문 연동 전 페이퍼 인출 — 런타임 메모리 차감,
    투표 삭제는 SQLite 영속. 전원 회수 시 자본 0 → 생성자가 펀드 삭제 가능.)

    Returns: {redeemed, remaining, fund_equity} | None(참여 내역 없음)
    """
    with _lock:
        rt = _rt(fund)
        _mark_to_market(fund)
        votes = store.get_votes(fund['id'])
        mine = next((v for v in votes if v['user'] == user), None)
        if not mine:
            return None
        total_dep = sum(v['deposit'] for v in votes) or 0
        share = (mine['deposit'] / total_dep) if total_dep else 1.0
        eq = rt['equity']
        redeemed = eq * share
        keep = max(0.0, 1.0 - share)
        # 자본/초기/손익을 같은 비율로 축소 → 남은 참가자 가치·수익률 불변
        rt['equity'] = eq * keep
        rt['initial'] = rt['initial'] * keep
        rt['asset_pnl'] = {c: p * keep for c, p in rt['asset_pnl'].items()}

        store.delete_vote(fund['id'], user)
        remaining = store.get_votes(fund['id'])
        if remaining:
            _aggregate(fund)
        else:
            # 전원 회수 → 빈 펀드 (비중 0, 전액 현금, 자본 0)
            for c in fund['universe']:
                rt['weights'][c] = 0.0
            rt['last_target'] = None
            rt['target_cash'] = 100.0
        _mark_to_market(fund)
        _save_runtime(fund, force=True)  # 회수 결과 즉시 영속
        return {'redeemed': round(redeemed, 2),
                'remaining': len(remaining),
                'fund_equity': round(rt['equity'], 2)}


def drop_runtime(fund_id):
    """펀드 삭제 시 런타임 캐시 정리. (영속 스냅샷은 store.delete_fund가 제거)"""
    with _lock:
        _runtime.pop(fund_id, None)
        _last_save.pop(fund_id, None)
