# -*- coding: utf-8 -*-
"""
alpha(EMA 수렴 속도) 검증 + 투표주기 적응형 alpha
"""
import math

MAX_W = 80
TARGET = -60.0   # 풀 숏 목표
START  = 25.0    # 초기 롱

def converge(alpha, target, start, steps):
    cur = start
    hist = [start]
    for _ in range(steps):
        cur = alpha*target + (1-alpha)*cur
        cur = max(-MAX_W, min(MAX_W, cur))
        hist.append(cur)
    return hist

print("="*72)
print("  검증 A: alpha별 전환 속도 (주간 투표 기준, 매주 '풀 숏' 목표)")
print("="*72)
print(f"\n  초기 {START:+.0f}% (롱) → 목표 {TARGET:+.0f}% (숏)\n")
print(f"  {'주차':>4}", end="")
for a in [0.6, 0.8, 0.9, 1.0]:
    print(f"{'alpha='+str(a):>12}", end="")
print()
hists = {a: converge(a, TARGET, START, 4) for a in [0.6, 0.8, 0.9, 1.0]}
for week in range(5):
    print(f"  {week:>4}", end="")
    for a in [0.6, 0.8, 0.9, 1.0]:
        v = hists[a][week]
        mark = "숏" if v < 0 else "롱"
        print(f"{v:>+9.1f}%{mark}", end="")
    print()
print("\n  → alpha=1.0: 1주만에 바로 목표. '내가 숏 찍으면 이번주에 숏' 보장")
print("  → alpha=0.6: 2주 걸려 숏 전환. 트레이딩엔 너무 느림")

print("\n" + "="*72)
print("  검증 B: 투표주기 적응형 alpha")
print("="*72)
print("""
  아이디어: 달력 기준 수렴 속도를 일정하게.
    - 주간 투표 → 다음 투표까지 1주 → 이번주에 확 반영해야 (alpha 높게)
    - 일간 투표 → 내일 또 투표 → 천천히 반영해도 됨 (alpha 낮게)

  공식:  alpha = 1 - (남길비율) ^ (투표주기 / 목표수렴기간)
         목표: '수렴기간(T) 안에 90% 도달' → 남길비율 0.1
""")

def adaptive_alpha(period_days, T_converge_days=7, leftover=0.1):
    return 1 - leftover ** (period_days / T_converge_days)

print(f"  목표: 7일 안에 90% 수렴 (어떤 주기든 동일)\n")
print(f"  {'투표주기':>10}{'→ alpha':>12}{'하루 한 발자국 크기':>20}")
for period, label in [(7,'주간'),(3,'3일'),(1,'일간'),(0.25,'6시간')]:
    a = adaptive_alpha(period)
    print(f"  {label:>8}({period:>4}일){a:>10.3f}")

print("\n  → 주간은 alpha 0.9 (확 바뀜), 일간은 0.28 (살살), 근데...")

print("\n" + "="*72)
print("  검증 C: 적응형 alpha면 '달력 시간' 수렴은 똑같다")
print("="*72)
print(f"\n  초기 {START:+.0f}% → 목표 {TARGET:+.0f}%, 둘 다 '7일 안에 90% 도달' 설정\n")

# 주간: 7일마다 1스텝, 일간: 1일마다 1스텝
a_week = adaptive_alpha(7)
a_day  = adaptive_alpha(1)

print(f"  [주간 투표] alpha={a_week:.3f}")
cur = START
for d in range(0, 15, 7):
    print(f"    {d:>2}일차: {cur:>+7.1f}%")
    cur = a_week*TARGET + (1-a_week)*cur

print(f"\n  [일간 투표] alpha={a_day:.3f}")
cur = START
for d in range(15):
    if d % 2 == 0:  # 이틀마다 출력
        mark = "숏" if cur < 0 else "롱"
        print(f"    {d:>2}일차: {cur:>+7.1f}% [{mark}]", end="")
        if d == 0: print("  ← 시작")
        elif d == 6: print("  ← 7일차쯤 둘 다 비슷한 위치")
        else: print()
    cur = a_day*TARGET + (1-a_day)*cur

print("""
  → 핵심: 일간 투표는 한 발자국은 작아도(0.28), 매일 밟으니까
          7일 지나면 주간 투표(0.9 한 방)랑 거의 같은 자리.
          그리고 일간은 중간에 마음 바뀌면 바로 다음날 반영 → 더 유연.
""")

print("="*72)
print("  결론")
print("="*72)
print("""
  ✅ alpha를 투표주기에 비례시키면:
     - 주간 투표: 이번주에 확 반영 (안 그러면 일주일 날림)
     - 일간 투표: 살살 반영하되 매일 누적 → 같은 속도 + 더 유연
  ✅ 어떤 주기를 택해도 '달력 기준' 반응속도는 운영자가 정한 T(수렴기간)로 고정
  ✅ 사용자 체감: "내 투표가 합리적인 시간 안에 반영된다"가 항상 보장
""")
