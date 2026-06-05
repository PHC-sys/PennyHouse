// USDC 6 decimals 변환
export const toUSDC = (amount: string) =>
  BigInt(Math.floor(parseFloat(amount) * 1_000_000));

export const fromUSDC = (amount: bigint) =>
  (Number(amount) / 1_000_000).toFixed(6);

// % → bps 변환 (10% → 1000)
export const toBps = (percent: string) =>
  Math.round(parseFloat(percent) * 100);

// 날짜 → unix timestamp
export const toTimestamp = (dateStr: string) =>
  Math.floor(new Date(dateStr).getTime() / 1000);

// unix timestamp → 날짜 문자열
export const fromTimestamp = (ts: bigint) =>
  new Date(Number(ts) * 1000).toLocaleDateString("ko-KR");

// 주소 축약
export const shortAddr = (addr: string) =>
  `${addr.slice(0, 6)}...${addr.slice(-4)}`;

// Act/360 쿠폰 계산 (토큰 1개당, 6 decimals)
export const calcCouponPerToken = (
  couponRateBps: number,
  fromDate: string,
  toDate: string
) => {
  const actualDays =
    (new Date(toDate).getTime() - new Date(fromDate).getTime()) /
    (1000 * 60 * 60 * 24);
  return Math.floor((1_000_000 * couponRateBps * actualDays) / (360 * 10_000));
};

// 마지막 지급 (원금 + 쿠폰)
export const calcFinalPerToken = (
  couponRateBps: number,
  fromDate: string,
  toDate: string
) => 1_000_000 + calcCouponPerToken(couponRateBps, fromDate, toDate);
