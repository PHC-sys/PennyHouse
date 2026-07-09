# -*- coding: utf-8 -*-
"""
펀드별 페이퍼 운용 엔진 (멀티펀드) — 이벤트 원장 + 결정론적 NAV 재구성.

진실의 원천 = 불변 이벤트 원장(store.fund_events): 비중이 바뀔 때마다 rebalance,
참가자 출금 시 redeem 기록. equity/NAV/손익은 메모리에 누적하지 않고 매번
원장+정규가격으로 재구성(api/nav.py)한다 → 재시작·다중인스턴스 무관, 결정론적.
런타임(_runtime)은 현재 비중/정산 등 표시용 캐시일 뿐 진실이 아니다.
실펀드(5차)에선 원장 대신 HL clearinghouseState를 읽어 같은 엔진을 재사용.
"""
import time
import threading

from governance.engine import (
    FUND_PROFILES, adaptive_alpha, simulate_votes, votes_to_target,
    liquidation_price, compute_volatility, fetch_universe, delisted_map,
)
from governance.engine.voting import apply_ema
from governance.api import store, live, nav

_INITIAL = 100_000.0
_lock = threading.Lock()
_runtime = {}       # fund_id -> {weights, settled, target_cash, last_target, initial}
_nav_cache = {}     # fund_id -> (ts, reconstruct결과)  재구성 메모(부하 완화)
_NAV_TTL = 4.0
_vol_cache = {}     # symbol -> (ts, vol)
_VOL_TTL = 1800


def _pnlpct(pnl, basis):
    """손익 기여도(%) — 기준자본 0(전원 회수)일 때 0 나눗셈 방지."""
    return round(pnl / basis * 100, 2) if basis and basis > 1e-9 else 0.0


def _vol(symbol):
    c = _vol_cache.get(symbol)
    if c and time.time() - c[0] < _VOL_TTL:
        return c[1]
    v = compute_volatility(symbol) or 0.05
    _vol_cache[symbol] = (time.time(), v)
    return v


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


def _fresh_runtime(fund):
    uni = fund['universe']
    init = fund.get('initial_deposit') or _INITIAL
    iw = fund.get('init_weights') or {}
    weights = ({c: float(iw.get(c, 0)) for c in uni} if iw
               else {c: 100.0 / len(uni) for c in uni})  # 균등 롱
    return {'weights': weights, 'settled': {}, 'target_cash': 0.0,
            'last_target': None, 'initial': init}


def _reconcile_delisted(fund, rt):
    """보유 자산이 상장폐지되면 settle-to-cash: 비중 0(현금 흡수), settled 기록.
    HL이 진실의 원천이라 재시작해도 delisted_map으로 복원(멱등)."""
    dl = delisted_map()
    if not dl:
        return
    for c in fund['universe']:
        if c in dl and c not in rt['settled']:
            info = dl[c]
            rt['settled'][c] = {'final_price': info.get('final_price'),
                                'ts': int(time.time()), 'successor': info.get('successor')}
            rt['weights'][c] = 0.0


def _active(fund, rt):
    """정산되지 않은(운용 중) 자산만."""
    return [c for c in fund['universe'] if c not in rt['settled']]


def _compute_target(fund, votes, active):
    """투표 → 목표 비중 + 현금비율 (순수, EMA 미적용). Returns (target|None, cash_pct)."""
    if not votes:
        return None, 0.0
    total_dep = sum(v['deposit'] for v in votes) or 1
    cash_pct = sum(v['deposit'] * float(v['votes'].get('_cash', 0)) for v in votes) / total_dep
    cash_pct = max(0.0, min(100.0, cash_pct))
    vr = simulate_votes(votes, active)
    vol_map = {c: _vol(c) for c in active}
    target = votes_to_target(vr, active, vol_map)
    if target is not None:
        scale = (100.0 - cash_pct) / 100.0
        target = {c: target[c] * scale for c in active}
    return target, cash_pct


def _aggregate(fund):
    """저장된 투표 → 목표 비중 + EMA 한 스텝 (rt['weights'] 갱신)."""
    fid = fund['id']
    rt = _runtime[fid]
    active = _active(fund, rt)
    votes = store.get_votes(fid)
    target, cash = _compute_target(fund, votes, active)
    rt['target_cash'] = cash
    rt['last_target'] = target
    if target is None:
        return
    profile = FUND_PROFILES[fund['profile']]
    alpha = adaptive_alpha(7, profile['T_CONVERGE'])
    rt['weights'] = apply_ema(rt['weights'], target, alpha, profile['MAX_WEIGHT'], active)
    for c in rt['settled']:        # apply_ema는 active만 반환 → 정산 키(0) 복원
        rt['weights'].setdefault(c, 0.0)


def _log_rebalance(fund, t=None):
    """현재 비중을 불변 이벤트로 기록 (NAV 재구성의 구간 경계)."""
    rt = _runtime[fund['id']]
    w = {c: round(rt['weights'].get(c, 0.0), 6) for c in fund['universe']}
    store.append_event(fund['id'], int(t or time.time()), 'rebalance',
                       {'weights': w, 'leverage': _leverage(fund),
                        'cash': round(rt.get('target_cash', 0.0), 4)})


def _invalidate(fid):
    _nav_cache.pop(fid, None)


def _rt(fund):
    """런타임 캐시 (없으면 이벤트 원장에서 현재 비중 복원 + 최초 백필)."""
    fid = fund['id']
    if fid in _runtime:
        return _runtime[fid]
    live.ensure_ctx(fund['universe'])  # 보유 자산 markPx 라이브 구독
    rt = _fresh_runtime(fund)
    _runtime[fid] = rt
    _reconcile_delisted(fund, rt)
    uni = fund['universe']
    reb = [e for e in store.get_events(fid) if e['kind'] == 'rebalance']
    if reb:
        last = reb[-1]['data']
        rt['weights'] = {c: float(last.get('weights', {}).get(c, 0.0)) for c in uni}
        rt['target_cash'] = float(last.get('cash', 0.0) or 0.0)
        rt['last_target'], _ = _compute_target(fund, store.get_votes(fid), _active(fund, rt))
    else:
        # 최초 전환(cutover): 구 스냅샷 비중 우선 → 없으면 투표 집계
        snap = store.load_runtime(fid)
        if snap and snap.get('weights'):
            rt['weights'] = {c: float(snap['weights'].get(c, 0.0)) for c in uni}
            rt['target_cash'] = float(snap.get('target_cash', 0.0) or 0.0)
            rt['last_target'], _ = _compute_target(fund, store.get_votes(fid), _active(fund, rt))
        else:
            _aggregate(fund)
        if store.get_votes(fid):  # 활성 펀드면 최초 rebalance 기록(펀드 개설시각)
            _log_rebalance(fund, t=int(fund.get('created_at') or time.time()))
    return rt


def _reconstruct(fund, force=False):
    """이벤트 원장+가격으로 NAV/equity/손익 재구성 (4초 메모)."""
    fid = fund['id']
    now = time.time()
    c = _nav_cache.get(fid)
    if not force and c and now - c[0] < _NAV_TTL:
        return c[1]
    rt = _rt(fund)
    events = store.get_events(fid)
    res = nav.reconstruct(fund, events, _registry(),
                          live.get_marks(fund['universe']), rt['initial'])
    _nav_cache[fid] = (now, res)
    return res


def submit_vote(fund, user, deposit, votes):
    uni = fund['universe']
    cash = max(0.0, min(100.0, float(votes.get('cash', 0) or 0)))
    votes = {c: int(votes.get(c, 0)) for c in uni}
    votes['_cash'] = cash
    with _lock:
        store.upsert_vote(fund['id'], user, float(deposit), votes)
        _rt(fund)
        _aggregate(fund)
        _log_rebalance(fund)   # 비중 변화 → 새 구간 경계 기록
        _invalidate(fund['id'])


def current_equity(fund):
    """현재 평가 자산 (삭제 가능 여부=자금 0 판단용)."""
    with _lock:
        res = _reconstruct(fund)
        return res['equity'] if res else _rt(fund)['initial']


def redeem(fund, user):
    """
    참가자 지분 회수(출금/탈퇴). 그의 share만큼 인출하고 투표 삭제 + redeem 이벤트
    기록(원장). NAV 재구성이 keep 배율로 자본·기준·손익을 동시 축소 → 남은 참가자
    수익률 불변. 전원 회수 시 자본 0 → 생성자가 펀드 삭제 가능.
    (실주문 연동 전 페이퍼 인출. 원장 기록이라 재시작에도 유지)
    """
    fid = fund['id']
    with _lock:
        rt = _rt(fund)
        res = _reconstruct(fund, force=True)
        eq = res['equity'] if res else rt['initial']
        votes = store.get_votes(fid)
        mine = next((v for v in votes if v['user'] == user), None)
        if not mine:
            return None
        total_dep = sum(v['deposit'] for v in votes) or 0
        share = (mine['deposit'] / total_dep) if total_dep else 1.0
        redeemed = eq * share
        keep = max(0.0, 1.0 - share)
        store.append_event(fid, int(time.time()), 'redeem', {'keep': keep, 'user': user})
        store.delete_vote(fid, user)
        remaining = store.get_votes(fid)
        if remaining:
            _aggregate(fund)
        else:  # 전원 회수 → 빈 펀드 (비중 0, 전액 현금)
            for c in fund['universe']:
                rt['weights'][c] = 0.0
            rt['last_target'] = None
            rt['target_cash'] = 100.0
        _log_rebalance(fund)
        _invalidate(fid)
        return {'redeemed': round(redeemed, 2), 'remaining': len(remaining),
                'fund_equity': round(eq * keep, 2)}


def get_state(fund):
    with _lock:
        rt = _rt(fund)
        _reconcile_delisted(fund, rt)
        res = _reconstruct(fund)
        uni = fund['universe']
        lev = _leverage(fund)
        reg = _registry()
        marks = live.get_marks(uni)

        if res:
            eq, basis = res['equity'], res['basis']
            apnl, avg = res['asset_pnl'], res['avg_entry']
            ret = res['ret_pct']
            series = nav.downsample(res['nav_series'], 300)
        else:  # 아직 투표 전 → 평탄
            eq = basis = rt['initial']
            apnl, avg, ret, series = {c: 0.0 for c in uni}, {}, 0.0, []

        votes = store.get_votes(fund['id'])
        total_dep = sum(v['deposit'] for v in votes) or 0
        participants = []
        for v in votes:
            share = v['deposit'] / total_dep if total_dep else 0
            participants.append({
                'user': v['user'], 'deposit': v['deposit'],
                'share_pct': round(share * 100, 1), 'votes': v['votes'],
                'paper_value': round(eq * share, 2), 'ret_pct': ret,
            })
        participants.sort(key=lambda x: x['paper_value'], reverse=True)

        carry_annual = 0.0
        assets = {}
        gross = 0.0
        for c in uni:
            if c in rt['settled']:
                s = rt['settled'][c]
                assets[c] = {
                    'weight': 0.0, 'settled': True,
                    'final_price': (round(s['final_price'], 4) if s.get('final_price') else None),
                    'successor': s.get('successor'),
                    'return_pct': _pnlpct(apnl.get(c, 0.0), basis),
                    'funding_carry': 0.0, 'avg_entry': None, 'price': None,
                    'liq_price': None, 'liq_dist_pct': None,
                    'max_leverage': reg.get(c, {}).get('max_leverage') or lev,
                    'eff_leverage': lev, 'quote': reg.get(c, {}).get('quote', 'USDC'),
                }
                continue
            w = rt['weights'].get(c, 0.0)
            gross += abs(w)
            amax = reg.get(c, {}).get('max_leverage') or lev
            elev = min(lev, amax)
            mmr = 1 / (2 * amax)
            ann = reg.get(c, {}).get('funding_annual', 0)
            contrib = -(w / 100) * elev * ann
            carry_annual += contrib
            entry = avg.get(c)
            side = 'long' if w >= 0 else 'short'
            liq = (liquidation_price(entry, elev, side, mmr)
                   if entry and abs(w) > 1e-9 and elev > 1 else None)
            px = marks.get(c)
            liq_dist = round(abs(px - liq) / px * 100, 1) if liq and px else None
            # 수익률 = 평단 대비 포지션 ROE% (방향×(현재가/평단−1)×레버) — 거래소 포지션 표시 방식.
            # ※ asset_pnl/basis(경로의존 펀드기여분)가 아님. 그건 펀드 전체수익률(ret)로만 반영.
            pos_ret = (round((1 if w >= 0 else -1) * (px / entry - 1) * elev * 100, 2)
                       if entry and px and entry > 0 and abs(w) > 1e-9 else 0.0)
            assets[c] = {
                'weight': round(w, 1), 'return_pct': pos_ret,
                'funding_carry': round(contrib, 2),
                'avg_entry': round(entry, 4) if entry else None,
                'price': px, 'liq_price': round(liq, 4) if liq else None,
                'liq_dist_pct': liq_dist, 'max_leverage': amax, 'eff_leverage': elev,
                'quote': reg.get(c, {}).get('quote', 'USDC'),
            }

        cash_pct = round(max(0.0, 100 - gross), 1)
        target_cash = round(rt.get('target_cash', 0.0), 1)
        lt = rt.get('last_target')
        return {
            'fund': {k: fund[k] for k in ('id', 'name', 'kind', 'visibility',
                                          'profile', 'universe')},
            'leverage': lev, 'fund_equity': round(eq, 2), 'fund_return_pct': ret,
            'funding_carry_annual_pct': round(carry_annual, 2),
            'cash_pct': cash_pct, 'target_cash_pct': target_cash,
            'weights': {c: round(rt['weights'].get(c, 0.0), 1) for c in uni},
            'target': (None if lt is None else {c: round(lt.get(c, 0.0), 1) for c in uni}),
            'assets': assets, 'participants': participants,
            'nav_history': series, 'prices': marks,
        }


def reset_fund(fund):
    """펀드 운용 상태 초기화 (투표/NAV/이벤트 삭제, 메타 유지)."""
    with _lock:
        fid = fund['id']
        import governance.api.store as st
        with st._lock, st._conn() as c:
            c.execute("DELETE FROM votes WHERE fund_id=?", (fid,))
            c.execute("DELETE FROM nav_history WHERE fund_id=?", (fid,))
            c.execute("DELETE FROM fund_events WHERE fund_id=?", (fid,))
        store.delete_runtime(fid)
        _runtime.pop(fid, None)
        _nav_cache.pop(fid, None)


def drop_runtime(fund_id):
    """펀드 삭제 시 런타임 캐시 정리. (영속은 store.delete_fund가 제거)"""
    with _lock:
        _runtime.pop(fund_id, None)
        _nav_cache.pop(fund_id, None)
