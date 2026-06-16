# -*- coding: utf-8 -*-
"""
NAV 재구성 엔진 — 이벤트 원장 + 정규 캔들가격으로 NAV/손익을 '계산'한다.

설계 원칙 (전문 금융 플랫폼):
  파생값(equity/NAV/손익)을 메모리에 누적하지 않는다. 진실의 원천은
  불변 이벤트 원장(rebalance/redeem)이고, NAV는 그 원장을 HL 정규 가격에
  replay한 '순수 함수'다. → 결정론적(같은 입력=같은 출력), 재시작·다중인스턴스
  무관, 감사 가능. 실펀드(5차)에선 원장 대신 HL clearinghouseState를 읽어
  같은 투영 엔진을 재사용한다.

equity(t) = initial × Π[구간] (1 + Σ_coin w·eff_lev·(가격_끝/가격_시작 − 1))
            × Π[회수] keep_factor
  · 구간 경계 = rebalance 이벤트 시각
  · 과거 가격 = HL 캔들 종가(정규), 현재 점 = 라이브 markPx (마지막 보정)
  · eff_lev = min(펀드레버, 자산max)  (HIP-3 자산 캡 반영)
  · 회수(redeem): equity·basis·손익을 keep 배율로 동시 축소 → 남은 참가자 수익률 불변
"""
import time
import pandas as pd

from governance.engine import fetch_candles


def _interval_for_span(seconds):
    """기간에 맞춰 캔들 간격 선택 (최근=촘촘, 과거=성김 → 비용/정밀 균형)."""
    days = seconds / 86400
    if days <= 1.5:
        return '1m'
    if days <= 10:
        return '5m'
    if days <= 60:
        return '1h'
    return '1d'


def _price_frame(coins, t0, now):
    """코인별 캔들 종가를 공통 시간그리드로 정렬 (정규 가격원, t0 이전 버퍼 포함)."""
    interval = _interval_for_span(now - t0)
    span_days = max(1, (now - t0) // 86400 + 2)
    closes = {}
    for c in coins:
        df = fetch_candles(c, days=span_days, interval=interval)
        if df is not None and len(df):
            closes[c] = df['close']
    if not closes:
        return None
    return pd.DataFrame(closes).sort_index().ffill()


def reconstruct(fund, events, reg, live_marks, initial):
    """
    이벤트 원장 + 캔들가격 → NAV/equity/자산손익 (결정론적).

    Returns dict | None:
        equity, basis(현 기준자본), asset_pnl{}, weights{}, leverage,
        avg_entry{}(현 구간 진입가), ret_pct, nav_series[{t,value,ret_pct}]
    """
    rebs = [(e['t'], e['data'].get('weights', {}), e['data'].get('leverage') or 1)
            for e in events if e['kind'] == 'rebalance']
    if not rebs:
        return None
    rebs.sort(key=lambda x: x[0])
    redeems = sorted((e['t'], float(e['data'].get('keep', 1.0)))
                     for e in events if e['kind'] == 'redeem')

    coins = fund['universe']
    t0 = rebs[0][0]
    now = int(time.time())

    def eff_lev(c, lev):
        amax = reg.get(c, {}).get('max_leverage') or lev
        return min(lev, amax)

    def _entry_at(tsec):
        """해당 rebalance 시각의 진입가 (asof) — 평단."""
        return price.asof(pd.to_datetime(tsec, unit='s', utc=True))

    price = _price_frame(coins, t0, now)
    if price is None:
        # 캔들 없음 → 라이브 마크를 진입가로, 평탄
        entry = {c: live_marks.get(c) for c in coins}
        return {'equity': float(initial), 'basis': float(initial),
                'asset_pnl': {c: 0.0 for c in coins}, 'weights': rebs[-1][1],
                'leverage': rebs[-1][2], 'avg_entry': entry, 'ret_pct': 0.0,
                'nav_series': [{'t': now, 'value': round(float(initial), 2), 'ret_pct': 0.0}]}

    t0_ts = pd.to_datetime(t0, unit='s', utc=True)
    grid = price[price.index > t0_ts]      # 펀드 시작 이후 구간만 replay
    equity = float(initial)
    basis = float(initial)                 # 회수로 줄어드는 기준자본 (수익률 분모)
    asset_pnl = {c: 0.0 for c in coins}
    series = []
    prev_row = price.asof(t0_ts)           # 시작가 (t0 시점 asof)
    prev_sec = t0
    ri = 0                                 # redeem 포인터
    rbi = 0                                # 활성 rebalance 인덱스
    entry_row = _entry_at(t0)              # 현 구간 진입가 (평단)

    for ts, row in grid.iterrows():
        tsec = int(ts.timestamp())
        while rbi + 1 < len(rebs) and rebs[rbi + 1][0] <= tsec:
            rbi += 1
            entry_row = _entry_at(rebs[rbi][0])
        w, lev = rebs[rbi][1], rebs[rbi][2]
        seg = 0.0
        for c in coins:
            p0, p1 = prev_row.get(c), row.get(c)
            if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                pnl = (w.get(c, 0) / 100) * equity * eff_lev(c, lev) * (p1 / p0 - 1)
                asset_pnl[c] += pnl
                seg += pnl
        equity += seg
        while ri < len(redeems) and prev_sec < redeems[ri][0] <= tsec:
            keep = redeems[ri][1]
            equity *= keep
            basis *= keep
            for c in asset_pnl:
                asset_pnl[c] *= keep
            ri += 1
        series.append({'t': tsec, 'value': round(equity, 2),
                       'ret_pct': round((equity / basis - 1) * 100, 4) if basis > 1e-9 else 0.0})
        prev_row, prev_sec = row, tsec

    # 마지막 캔들 이후 발생한 회수 반영
    while ri < len(redeems) and redeems[ri][0] <= now:
        keep = redeems[ri][1]
        equity *= keep
        basis *= keep
        for c in asset_pnl:
            asset_pnl[c] *= keep
        ri += 1
    # 마지막 캔들 이후 rebalance 반영
    while rbi + 1 < len(rebs) and rebs[rbi + 1][0] <= now:
        rbi += 1
        entry_row = _entry_at(rebs[rbi][0])
    w, lev = rebs[rbi][1], rebs[rbi][2]
    # 라이브 팁: 마지막 가격 → 현재 markPx (진행 중인 봉, 매 요청 실시간)
    if live_marks and prev_row is not None:
        seg = 0.0
        for c in coins:
            p0, p1 = prev_row.get(c), live_marks.get(c)
            if pd.notna(p0) and p1 and p0 > 0:
                pnl = (w.get(c, 0) / 100) * equity * eff_lev(c, lev) * (p1 / p0 - 1)
                asset_pnl[c] += pnl
                seg += pnl
        equity += seg
        ret = round((equity / basis - 1) * 100, 4) if basis > 1e-9 else 0.0
        if series and now - series[-1]['t'] < 60:
            series[-1] = {'t': now, 'value': round(equity, 2), 'ret_pct': ret}
        else:
            series.append({'t': now, 'value': round(equity, 2), 'ret_pct': ret})

    # 현 구간 진입가(평단) = 활성 rebalance 시작 시점 가격
    avg_entry = {}
    if entry_row is not None:
        for c in coins:
            v = entry_row.get(c)
            avg_entry[c] = float(v) if pd.notna(v) else None

    ret_pct = round((equity / basis - 1) * 100, 4) if basis > 1e-9 else 0.0
    return {'equity': equity, 'basis': basis, 'asset_pnl': asset_pnl,
            'weights': w, 'leverage': lev, 'avg_entry': avg_entry,
            'ret_pct': ret_pct, 'nav_series': series}


def downsample(series, n=300):
    """차트 응답용 다운샘플 (마지막 점은 보존)."""
    if len(series) <= n:
        return series
    k = len(series) / n
    out = [series[int(i * k)] for i in range(n)]
    if out[-1] is not series[-1]:
        out.append(series[-1])
    return out
