# -*- coding: utf-8 -*-
"""
02번 엔진(적응형 alpha 반영) 자체 검증.
노트북 cell-imports / cell-engine 과 동일한 함수를 복제해 assert로 검증.
실제 HL 데이터로 백테스트까지 돌려 Perfect 우위·주기 불변성 확인.
"""
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timezone

VOLATILITY = {'BTC': 0.030, 'ETH': 0.040, 'SOL': 0.055, 'HYPE': 0.070}
COINS = list(VOLATILITY.keys())
FUND_PROFILES = {
    'aggressive':  {'T_CONVERGE': 7,  'MAX_WEIGHT': 80, 'FUND_LEVERAGE': 5},
    'conservative':{'T_CONVERGE': 21, 'MAX_WEIGHT': 60, 'FUND_LEVERAGE': 2},
}
REBALANCE_FEE = 0.0002
LOOKBACK = 14

def adaptive_alpha(period_days, T_converge_days, leftover=0.1):
    period_days = max(period_days, 1e-9)
    return 1 - leftover ** (period_days / T_converge_days)

def simulate_votes(participants, coins):
    total = sum(p['deposit'] for p in participants)
    return {c: {'score': sum(p['votes'].get(c,0)*p['deposit']/total for p in participants)/2}
            for c in coins}

def votes_to_target(vr):
    raw = {c: vr[c]['score'] * (0.03/VOLATILITY[c]) for c in COINS}
    tot = sum(abs(v) for v in raw.values())
    if tot < 1e-9: return None
    return {c: raw[c]/tot*100 for c in COINS}

def score_to_vote(x):
    if x >  0.5: return 2
    if x >  0.1: return 1
    if x < -0.5: return -2
    if x < -0.1: return -1
    return 0

def gen_momentum(win, ps):
    for p in ps:
        for c in COINS: p['votes'][c] = score_to_vote(win[c].sum()/0.1)
    return ps
def gen_contrarian(win, ps):
    for p in ps:
        for c in COINS: p['votes'][c] = score_to_vote(-win[c].sum()/0.1)
    return ps
def gen_random(ps, seed):
    rng = np.random.default_rng(seed)
    for p in ps:
        for c in COINS: p['votes'][c] = int(rng.choice([-2,-1,0,1,2],p=[.1,.2,.4,.2,.1]))
    return ps
def gen_perfect(fwd, ps):
    for p in ps:
        for c in COINS: p['votes'][c] = score_to_vote(fwd[c].sum()/0.1)
    return ps

def make_gen(s):
    def g(di, ps, past, fut):
        if s=='momentum':   return gen_momentum(past, ps)
        if s=='contrarian': return gen_contrarian(past, ps)
        if s=='perfect':    return gen_perfect(fut, ps)
        return gen_random(ps, di)
    return g

def run_backtest(name, gen, rdf, pname, tvl=100_000, period=7):
    pf = FUND_PROFILES[pname]
    alpha = adaptive_alpha(period, pf['T_CONVERGE'])
    ps = [{'name':'A','deposit':500,'votes':{}},
          {'name':'B','deposit':300,'votes':{}},
          {'name':'C','deposit':200,'votes':{}}]
    lev, cap = pf['FUND_LEVERAGE'], pf['MAX_WEIGHT']
    eq = tvl
    w = {c: 100.0/len(COINS) for c in COINS}
    hist, liq = [], False
    for di, date in enumerate(rdf.index):
        if di % period == 0 and di > 0:
            past = rdf.iloc[max(0,di-LOOKBACK):di]
            fut  = rdf.iloc[di:di+period]
            ps = gen(di, ps, past, fut)
            tgt = votes_to_target(simulate_votes(ps, COINS))
            if tgt is not None:
                nw = {c: float(np.clip(alpha*tgt[c]+(1-alpha)*w[c], -cap, cap)) for c in COINS}
                turn = sum(abs(nw[c]-w[c]) for c in COINS)/100
                eq -= turn*eq*lev*REBALANCE_FEE
                w = nw
        eq += sum((w[c]/100)*eq*lev*rdf.loc[date,c] for c in COINS)
        if eq < tvl*0.1 and not liq: liq = True
        hist.append({'equity':max(eq,0)})
    df = pd.DataFrame(hist, index=rdf.index)
    df['cum'] = (df['equity']/tvl-1)*100
    df['liq'] = liq
    return df

# ════════════════════════════════════════════════════════════════
print("="*72)
print("  TEST 1: adaptive_alpha 수학 검증")
print("="*72)
# 주간(7일), T=7 → alpha=0.9 (leftover 0.1^1)
a = adaptive_alpha(7, 7)
assert abs(a - 0.9) < 1e-9, f"기대 0.9, 실제 {a}"
print(f"  주간 T=7  → alpha={a:.4f}  (기대 0.9000) ✅")
# 일간(1일), T=7 → alpha=1-0.1^(1/7)
a = adaptive_alpha(1, 7)
exp = 1 - 0.1**(1/7)
assert abs(a - exp) < 1e-12
print(f"  일간 T=7  → alpha={a:.4f}  (기대 {exp:.4f}) ✅")
# 단조성: 주기 길수록 alpha 큼
assert adaptive_alpha(7,7) > adaptive_alpha(1,7) > adaptive_alpha(0.25,7)
print(f"  단조성: 주간 > 일간 > 6시간 alpha ✅")

print("\n" + "="*72)
print("  TEST 2: 달력 수렴 불변성 (주간 vs 일간, 7일 뒤 위치 유사)")
print("="*72)
TARGET, START, T = -60.0, 25.0, 7
# 주간 1스텝
aw = adaptive_alpha(7, T); cur_w = START
cur_w = aw*TARGET + (1-aw)*cur_w   # 7일 뒤
# 일간 7스텝
ad = adaptive_alpha(1, T); cur_d = START
for _ in range(7): cur_d = ad*TARGET + (1-ad)*cur_d
print(f"  주간(1스텝) 7일 뒤: {cur_w:+.1f}%")
print(f"  일간(7스텝) 7일 뒤: {cur_d:+.1f}%")
diff = abs(cur_w - cur_d)
assert diff < 3.0, f"7일 뒤 차이 {diff:.1f}%p — 너무 큼"
print(f"  차이 {diff:.2f}%p < 3%p → 달력 수렴 동일 ✅")

print("\n" + "="*72)
print("  TEST 3: votes_to_target 상식 검증")
print("="*72)
ps = [{'name':'big','deposit':6000,'votes':{'BTC':2,'ETH':0,'SOL':-1,'HYPE':1}},
      {'name':'me', 'deposit':3000,'votes':{'BTC':1,'ETH':2,'SOL':0,'HYPE':-1}},
      {'name':'sm', 'deposit':1000,'votes':{'BTC':-2,'ETH':1,'SOL':2,'HYPE':0}}]
tgt = votes_to_target(simulate_votes(ps, COINS))
assert tgt['BTC'] > 0,  "BTC 큰손 롱인데 숏?"
assert tgt['ETH'] > 0,  "ETH 다수 롱인데 숏?"
assert tgt['SOL'] < 0,  "SOL 큰손 숏인데 롱?"
assert tgt['HYPE'] > 0, "HYPE 큰손(60%) 롱이 이겨야"
assert abs(sum(abs(v) for v in tgt.values()) - 100) < 1e-6, "정규화 실패"
print(f"  BTC {tgt['BTC']:+.1f}(롱) ETH {tgt['ETH']:+.1f}(롱) "
      f"SOL {tgt['SOL']:+.1f}(숏) HYPE {tgt['HYPE']:+.1f}(롱) ✅")
print(f"  sum(abs)=100 정규화 ✅")
# 큰손 BTC 뒤집기
ps[0]['votes']['BTC'] = -2
tgt2 = votes_to_target(simulate_votes(ps, COINS))
assert tgt2['BTC'] < 0, "큰손 숏 전환했는데 BTC 롱?"
print(f"  큰손 BTC 롱→숏 전환 시 목표 {tgt['BTC']:+.1f}→{tgt2['BTC']:+.1f} ✅")

print("\n" + "="*72)
print("  TEST 4: 실제 HL 데이터로 백테스트 — Perfect 우위 검증")
print("="*72)
HL='https://api.hyperliquid.xyz/info'
def fetch(coin, days=180):
    end=int(datetime.now(timezone.utc).timestamp()*1000); start=end-days*86400*1000
    r=requests.post(HL,json={'type':'candleSnapshot','req':{'coin':coin,'interval':'1d',
        'startTime':start,'endTime':end}},timeout=15).json()
    df=pd.DataFrame(r); df['t']=pd.to_datetime(df['t'],unit='ms',utc=True)
    return df.set_index('t')['c'].astype(float)
print("  HL 가격 수집 중...")
closes=pd.DataFrame({c:fetch(c) for c in COINS}).dropna()
returns=closes.pct_change().fillna(0)
print(f"  데이터: {len(returns)}일 ({returns.index[0].date()}~{returns.index[-1].date()})")

bh = ((1+returns.mean(axis=1)).cumprod().iloc[-1]-1)*100
print(f"\n  Buy&Hold 벤치마크: {bh:+.1f}%\n")
for pname in FUND_PROFILES:
    print(f"  [{pname}]")
    res = {}
    for s in ['momentum','contrarian','random','perfect']:
        df = run_backtest(s, make_gen(s), returns, pname)
        res[s] = df['cum'].iloc[-1]
        print(f"    {s:<11} {res[s]:>+10.1f}%  {'청산' if df['liq'].iloc[-1] else ''}")
    assert res['perfect'] > res['momentum'], "Perfect가 모멘텀보다 못함?!"
    assert res['perfect'] > res['random'],   "Perfect가 랜덤보다 못함?!"
    assert res['perfect'] > bh,              "Perfect가 Buy&Hold보다 못함?!"
    print(f"    → Perfect가 모든 시나리오·벤치마크 압도 ✅\n")

print("="*72)
print("  TEST 5: 투표주기 바꿔도 Perfect는 여전히 이긴다 (주간/3일/일간)")
print("="*72)
for period in [7, 3, 1]:
    df = run_backtest('perfect', make_gen('perfect'), returns, 'aggressive', period=period)
    a = adaptive_alpha(period, 7)
    r = df['cum'].iloc[-1]
    assert r > bh, f"주기 {period}일에서 Perfect가 벤치마크보다 못함"
    print(f"  주기 {period}일 (alpha={a:.3f}): Perfect {r:>+12.1f}%  > B&H ✅")

print("\n" + "="*72)
print("  모든 검증 통과 — 적응형 alpha 엔진 정상 작동")
print("="*72)
