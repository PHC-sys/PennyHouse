# -*- coding: utf-8 -*-
"""
히스토리 시뮬레이션 엔진 — 임의 구간 + 포지션 스케줄 → NAV + 손익 분해.

설계: NAV/손익을 누적 상태가 아니라 (포지션 스케줄 + HL 정규 가격·펀딩)의
순수 함수로 계산(결정론·재현). nav.reconstruct(라이브 펀드용)의 일반화 —
  · 임의 과거 구간 [start, end]
  · 사용자/전략이 지정한 포지션 스케줄(언제 무엇을 롱/숏)
  · ★ 시간당 펀딩 적립 (HL은 매시간 정산) → 손익을 [가격]+[펀딩]으로 분해
  · 확률적 maker/taker 수수료 (리밸런싱 체결마다)

equity_t = initial × Π(1 + r_t) × Π(1 − fee_frac@리밸런싱)
  r_t = 가격수익률_t + 펀딩수익률_t  (시간 단위)
  가격_t   = Σ (w/100)·eff_lev·(p_t/p_{t-1} − 1)
  펀딩_t   = Σ −(w/100)·eff_lev·f_t   (롱=양의 펀딩 지불, 숏=수취)
  eff_lev = min(레버, 자산max)
이 엔진이 (a) '역사책' 시뮬레이터 (b) FSSC 백테스트의 공통 두뇌.
"""
import time
import numpy as np
import pandas as pd

from .prices import fetch_candles, fetch_funding_history


def _hourly_panel(assets, start, end):
    """자산별 시간당 종가·펀딩요율을 공통 시간그리드로 정렬."""
    idx = pd.date_range(pd.to_datetime(start, unit='s', utc=True).floor('h'),
                        pd.to_datetime(end, unit='s', utc=True).floor('h'), freq='h')
    span_days = max(1, (end - start) // 86400 + 2)
    price, funding = {}, {}
    for a in assets:
        c = fetch_candles(a, days=span_days, interval='1h')
        if c is not None and len(c):
            price[a] = c['close'].reindex(idx).ffill()
        f = fetch_funding_history(a, days=span_days)
        funding[a] = (f['fundingRate'].reindex(idx).ffill().fillna(0.0)
                      if f is not None and len(f) else pd.Series(0.0, index=idx))
    if not price:
        return None, None, None
    P = pd.DataFrame(price).reindex(idx).ffill().bfill()
    F = pd.DataFrame({a: funding[a] for a in P.columns}).reindex(idx).fillna(0.0)
    return idx, P, F


def _weight_matrix(positions, idx, cols):
    """리밸런싱 스케줄 → 시간그리드 비중·레버리지 행렬 (구간 ffill)."""
    wrows, levs = {}, {}
    for p in sorted(positions, key=lambda x: x['t']):
        snapped = idx[idx >= pd.to_datetime(p['t'], unit='s', utc=True)]
        if len(snapped) == 0:
            continue
        t0 = snapped[0]
        wrows[t0] = [float(p['weights'].get(a, 0.0)) for a in cols]
        levs[t0] = float(p.get('leverage', 1) or 1)
    if not wrows:
        return None, None
    W = pd.DataFrame.from_dict(wrows, orient='index', columns=cols).sort_index()
    W = W.reindex(idx, method='ffill').fillna(0.0)
    LEV = pd.Series(levs).sort_index().reindex(idx, method='ffill').ffill().bfill().fillna(1.0)
    return W, LEV


def hedge_beta(long_assets, short_assets, start, end=None):
    """
    롱바스켓 vs 숏바스켓 시간당 수익률 회귀 → 헷지비율 β + 헷지품질 R².
    β = cov(rL, rS)/var(rS).  숏:롱 노셔널 = β:1 이면 공통팩터(방향성) 상쇄.
    ※ 같은 구간 in-sample β (낙관적 — 룩어헤드). 전향 추정은 플립규칙 단계에서.
    """
    end = end or int(time.time())
    _, P, _ = _hourly_panel(long_assets + short_assets, start, end)
    if P is None or len(P) < 5:
        return None
    PR = P.pct_change().dropna()
    rL = PR[long_assets].mean(axis=1)   # 등가중 롱바스켓 수익률
    rS = PR[short_assets].mean(axis=1)
    var_s = float(rS.var())
    if var_s <= 0:
        return None
    beta = float(rL.cov(rS) / var_s)
    corr = float(rL.corr(rS))
    return {'beta': round(beta, 4), 'r2': round(corr * corr, 4), 'corr': round(corr, 4),
            'vol_long': round(float(rL.std()), 5), 'vol_short': round(float(rS.std()), 5)}


def beta_weights(long_assets, short_assets, beta, gross=200.0):
    """헷지비율 β로 비중 구성 (롱:숏 노셔널 = 1:β, gross 고정)."""
    b = max(beta, 1e-6)
    lw = gross / (1 + b) / len(long_assets)
    sw = -gross * b / (1 + b) / len(short_assets)
    w = {a: round(lw, 4) for a in long_assets}
    w.update({a: round(sw, 4) for a in short_assets})
    return w


def run_simulation(assets, positions, start, end=None, initial=100000.0,
                   reg=None, fees=None):
    """
    Args:
        assets: [symbol,...]
        positions: [{'t': sec, 'weights': {sym: signed_pct}, 'leverage': L}] 리밸런싱 스케줄
        start, end: epoch sec (end 기본=now)
        reg: {sym: {'max_leverage': n}} 자산 레버 캡 (옵션)
        fees: {'taker':0.00045,'maker':0.00015,'p_maker':0.5}  확률적 혼합(기대값)
    Returns dict | None:
        nav[{t,value,ret_pct}], totals{price,funding,fees,net,ret_pct},
        by_asset{sym:{price_pnl,funding_pnl}}, final_equity, mdd_pct
    """
    end = end or int(time.time())
    fees = fees or {}
    taker, maker = fees.get('taker', 0.00045), fees.get('maker', 0.00015)
    p_maker = fees.get('p_maker', 0.5)
    blended = p_maker * maker + (1 - p_maker) * taker  # 확률적 maker/taker 기대 수수료율

    idx, P, F = _hourly_panel(assets, start, end)
    if P is None or len(P) < 2:
        return None
    cols = list(P.columns)
    W, LEV = _weight_matrix(positions, idx, cols)
    if W is None:
        return None

    amax = {a: (reg.get(a, {}).get('max_leverage') if reg else None) for a in cols}
    EFF = pd.DataFrame(
        {a: (np.minimum(LEV.values, amax[a]) if amax[a] else LEV.values) for a in cols},
        index=idx)

    PR = P.pct_change().fillna(0.0)
    Wf, EFFv, PRv, Fv = W.values / 100.0, EFF.values, PR.values, F.values
    price_frac = (Wf * EFFv * PRv).sum(axis=1)        # 시간당 가격 수익률
    funding_frac = (-(Wf) * EFFv * Fv).sum(axis=1)    # 시간당 펀딩 수익률(부호 포함)
    r = price_frac + funding_frac

    dW = W.diff()
    dW.iloc[0] = W.iloc[0]                              # 최초 진입(0→W)도 체결
    fee_frac = (dW.abs().values / 100.0 * EFFv).sum(axis=1) * blended  # 리밸런싱 체결비용

    step_mult = (1 + r) * (1 - fee_frac)
    equity = initial * np.cumprod(step_mult)
    eq_prev = np.concatenate([[initial], equity[:-1]])  # 직전 자본 (손익 적립 기준)

    # 분해 (자산별 가격손익 / 펀딩손익)
    price_pnl = (eq_prev[:, None] * (Wf * EFFv * PRv)).sum(axis=0)
    funding_pnl = (eq_prev[:, None] * (-(Wf) * EFFv * Fv)).sum(axis=0)
    fees_total = float((eq_prev * fee_frac).sum())

    by_asset = {a: {'price_pnl': round(float(price_pnl[i]), 2),
                    'funding_pnl': round(float(funding_pnl[i]), 2)}
                for i, a in enumerate(cols)}
    final_eq = float(equity[-1])
    peak = np.maximum.accumulate(equity)
    mdd = float(((equity - peak) / peak).min() * 100)

    nav = [{'t': int(ts.timestamp()), 'value': round(float(e), 2),
            'ret_pct': round((e / initial - 1) * 100, 4)}
           for ts, e in zip(idx, equity)]

    return {
        'nav': nav, 'final_equity': round(final_eq, 2),
        'totals': {
            'price': round(float(price_pnl.sum()), 2),
            'funding': round(float(funding_pnl.sum()), 2),
            'fees': round(-fees_total, 2),
            'net': round(final_eq - initial, 2),
            'ret_pct': round((final_eq / initial - 1) * 100, 2),
        },
        'by_asset': by_asset, 'mdd_pct': round(mdd, 2),
        'hours': len(idx),
    }
