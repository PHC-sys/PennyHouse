"""
funding_history.py
==================
Hyperliquid 펀딩비 히스토리 조회 및 FundingCarryBond 수익성 분석

사용법:
    pip install requests pandas tabulate matplotlib
    python funding_history.py                      # 기본 (BTC, ETH, HYPE / 90일)
    python funding_history.py --coins BTC ETH SOL --days 180
    python funding_history.py --coins BTC --days 365 --chart
"""

import requests
import argparse
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ── 선택적 의존성 ──────────────────────────────────────────────
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ── 상수 ──────────────────────────────────────────────────────
HL_API = "https://api.hyperliquid.xyz/info"
FUNDING_INTERVALS_PER_YEAR = 3 * 365   # fundingHistory API는 8h 집계 반환 (3건/일)
                                       # 연환산 = 펀딩비 × 1,095
HEADERS = {"Content-Type": "application/json"}


# ── API 호출 ──────────────────────────────────────────────────
def fetch_funding_history(coin: str, days: int) -> list[dict]:
    """HL API에서 펀딩비 히스토리를 가져온다."""
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 24 * 60 * 60 * 1000

    payload = {
        "type": "fundingHistory",
        "coin": coin,
        "startTime": start_ms,
        "endTime": end_ms,
    }
    resp = requests.post(HL_API, headers=HEADERS, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # 파싱
    records = []
    for item in data:
        records.append({
            "coin":         coin,
            "time":         datetime.fromtimestamp(item["time"] / 1000, tz=timezone.utc),
            "funding_rate": float(item["fundingRate"]),   # 8시간 기준 소수
            "premium":      float(item.get("premium", 0)),
        })
    return records


# ── 통계 계산 ─────────────────────────────────────────────────
def calc_stats(records: list[dict]) -> dict:
    if not records:
        return {}

    rates = [r["funding_rate"] for r in records]
    n = len(rates)

    mean_8h   = sum(rates) / n
    ann_mean  = mean_8h * FUNDING_INTERVALS_PER_YEAR * 100   # %

    variance  = sum((r - mean_8h) ** 2 for r in rates) / n
    std_8h    = variance ** 0.5
    ann_std   = std_8h * (FUNDING_INTERVALS_PER_YEAR ** 0.5) * 100

    positive  = sum(1 for r in rates if r > 0)
    negative  = sum(1 for r in rates if r < 0)

    # 최악 연속 음수 구간 (숏 포지션 보유자가 내는 기간)
    max_neg_streak = cur_streak = 0
    for r in rates:
        if r < 0:
            cur_streak += 1
            max_neg_streak = max(max_neg_streak, cur_streak)
        else:
            cur_streak = 0

    # 누적 수익 (숏 포지션: 롱이 내는 펀딩비 수취)
    cumulative_pct = sum(rates) * 100   # %

    # 분기별 연환산 (최근 90개 구간 ≈ 30일)
    recent_90 = rates[-90:] if len(rates) >= 90 else rates
    ann_recent = (sum(recent_90) / len(recent_90)) * FUNDING_INTERVALS_PER_YEAR * 100

    sharpe = (ann_mean / ann_std) if ann_std > 0 else 0

    return {
        "coin":             records[0]["coin"],
        "period_days":      (records[-1]["time"] - records[0]["time"]).days,
        "data_points":      n,
        "mean_8h_bps":      mean_8h * 10000,          # bps
        "ann_mean_pct":     ann_mean,
        "ann_std_pct":      ann_std,
        "ann_recent_pct":   ann_recent,
        "sharpe":           sharpe,
        "positive_pct":     positive / n * 100,
        "negative_pct":     negative / n * 100,
        "max_neg_streak":   max_neg_streak,            # 연속 음수 최대 횟수
        "cumulative_pct":   cumulative_pct,
        "min_8h_pct":       min(rates) * 100,
        "max_8h_pct":       max(rates) * 100,
    }


# ── FundingCarryBond 시뮬레이션 ───────────────────────────────
def simulate_carry_bond(records: list[dict], coupon_rate_ann: float, fee_bps: float = 11.5):
    """
    단순 시뮬레이션:
      - 펀딩비 수익으로 coupon_rate_ann(%) 고정 쿠폰 지급 가능한지 검증
      - fee_bps: 진입/청산 비용 (기본 11.5bp)
    """
    if not records:
        return

    coupon_per_8h = coupon_rate_ann / 100 / FUNDING_INTERVALS_PER_YEAR
    fee_cost = fee_bps / 10000   # 원금 대비 총 비용

    reserve = 0.0          # 누적 잉여 (펀딩 수익 - 쿠폰 지급)
    shortfall_periods = 0

    for r in records:
        net = r["funding_rate"] - coupon_per_8h
        reserve += net
        if net < 0:
            shortfall_periods += 1

    n = len(records)
    net_after_fee = reserve - fee_cost

    print(f"\n{'=' * 55}")
    print(f"  FundingCarryBond 시뮬레이션 — {records[0]['coin']}")
    print(f"{'=' * 55}")
    print(f"  목표 쿠폰(연):      {coupon_rate_ann:.1f}%")
    print(f"  시뮬레이션 기간:    {n}회 ({n // (3*30):.0f}개월)")
    print(f"  누적 펀딩 수익:    {reserve * 100:+.2f}%  (원금 대비)")
    print(f"  진입·청산 비용:    -{fee_cost * 100:.2f}%")
    print(f"  순 수익 (수수료 후): {net_after_fee * 100:+.2f}%")
    print(f"  쿠폰 부족 구간:    {shortfall_periods}/{n}회 "
          f"({shortfall_periods/n*100:.1f}%)")
    verdict = "✅ 지급 가능" if net_after_fee > 0 else "❌ 적자"
    print(f"  종합 판단:          {verdict}")
    print(f"{'=' * 55}")


# ── 출력 ──────────────────────────────────────────────────────
def print_stats_table(stats_list: list[dict]):
    headers = [
        "Coin", "기간(일)", "연환산수익(%)", "최근30일연환산(%)",
        "연변동성(%)", "Sharpe", "양수비율(%)", "최대연속음수",
        "8h최소(%)", "8h최대(%)"
    ]
    rows = []
    for s in stats_list:
        rows.append([
            s["coin"],
            s["period_days"],
            f"{s['ann_mean_pct']:.2f}",
            f"{s['ann_recent_pct']:.2f}",
            f"{s['ann_std_pct']:.2f}",
            f"{s['sharpe']:.2f}",
            f"{s['positive_pct']:.1f}",
            s["max_neg_streak"],
            f"{s['min_8h_pct']:.4f}",
            f"{s['max_8h_pct']:.4f}",
        ])

    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
    else:
        print("\t".join(headers))
        for row in rows:
            print("\t".join(str(c) for c in row))


def plot_funding(all_records: dict[str, list], days: int):
    if not HAS_MATPLOTLIB:
        print("[경고] matplotlib 미설치 — 차트 생략. pip install matplotlib")
        return

    coins = list(all_records.keys())
    fig, axes = plt.subplots(len(coins), 1, figsize=(14, 4 * len(coins)), sharex=False)
    if len(coins) == 1:
        axes = [axes]

    for ax, coin in zip(axes, coins):
        records = all_records[coin]
        times = [r["time"] for r in records]
        rates = [r["funding_rate"] * 100 for r in records]   # %

        colors = ["#26a69a" if r >= 0 else "#ef5350" for r in rates]
        ax.bar(times, rates, color=colors, width=timedelta(hours=7.5))
        ax.axhline(0, color="white", linewidth=0.5, linestyle="--")

        mean_val = sum(rates) / len(rates)
        ax.axhline(mean_val, color="yellow", linewidth=1,
                   linestyle=":", label=f"평균 {mean_val:.4f}%")

        ax.set_title(f"{coin} — 8시간 펀딩비 히스토리 ({days}일)", color="white")
        ax.set_ylabel("펀딩비 (%)", color="white")
        ax.tick_params(colors="white")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.legend(facecolor="#1a1a2e", labelcolor="white")
        ax.set_facecolor("#0d1117")
        fig.patch.set_facecolor("#0d1117")

    plt.tight_layout()
    out_path = f"funding_chart_{'_'.join(coins)}_{days}d.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n[차트 저장] {out_path}")
    plt.show()


# ── 메인 ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Hyperliquid 펀딩비 분석")
    parser.add_argument("--coins", nargs="+", default=["BTC", "ETH", "HYPE"],
                        help="분석할 코인 (기본: BTC ETH HYPE)")
    parser.add_argument("--days",  type=int,   default=90,
                        help="조회 기간(일) (기본: 90)")
    parser.add_argument("--chart", action="store_true",
                        help="펀딩비 차트 출력")
    parser.add_argument("--simulate", type=float, default=None,
                        metavar="COUPON_PCT",
                        help="FundingCarryBond 시뮬레이션 (예: --simulate 8.0)")
    parser.add_argument("--save-json", action="store_true",
                        help="원본 데이터를 JSON으로 저장")
    args = parser.parse_args()

    print(f"\nHyperliquid 펀딩비 분석 — {args.coins} / 최근 {args.days}일\n")

    all_records = {}
    stats_list  = []

    for coin in args.coins:
        print(f"  [{coin}] 데이터 수집 중...", end=" ", flush=True)
        try:
            records = fetch_funding_history(coin, args.days)
            print(f"{len(records)}건")
            all_records[coin] = records
            stats_list.append(calc_stats(records))
        except Exception as e:
            print(f"오류: {e}")

    if not stats_list:
        print("데이터 없음. 종료.")
        return

    # 통계 테이블 출력
    print()
    print_stats_table(stats_list)

    # FundingCarryBond 시뮬레이션
    if args.simulate is not None:
        for coin in args.coins:
            if coin in all_records:
                simulate_carry_bond(all_records[coin], args.simulate)

    # 차트
    if args.chart:
        plot_funding(all_records, args.days)

    # JSON 저장
    if args.save_json:
        for coin, records in all_records.items():
            fname = f"funding_{coin}_{args.days}d.json"
            with open(fname, "w") as f:
                json.dump(
                    [{**r, "time": r["time"].isoformat()} for r in records],
                    f, indent=2
                )
            print(f"[저장] {fname}")


if __name__ == "__main__":
    main()
