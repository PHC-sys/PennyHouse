# StructuredBond v3 — 컨트랙트 설계 스펙

> 작성일: 2026-06-05  
> 상태: 구현 완료 / 테스트 45개 통과 / Sepolia 배포 전

---

## 목차

1. [설계 배경](#1-설계-배경)
2. [채권 유형](#2-채권-유형)
3. [전체 라이프사이클](#3-전체-라이프사이클)
4. [컨트랙트 변수](#4-컨트랙트-변수)
5. [함수 명세](#5-함수-명세)
6. [Reserve 설계](#6-reserve-설계)
7. [이중지급 방지](#7-이중지급-방지)
8. [경과이자](#8-경과이자)
9. [보안 설계](#9-보안-설계)
10. [BondFactory 연동](#10-bondfactory-연동)
11. [프론트엔드 연동 가이드](#11-프론트엔드-연동-가이드)
12. [v2 → v3 변경사항](#12-v2--v3-변경사항)

---

## 1. 설계 배경

### v2의 한계

```
v2 (StructuredBond):
  - 만기 시 원금+이자 일괄 지급 (이표채 불가)
  - 발행자가 Reserve 전액 사전 적립 (조달 의미 없음)
  - 30/360 고정 이자 계산 (달러 표준 미준수)
  - 발행 시점에 토큰 즉시 발행 (청약 구조 없음)
```

### v3 설계 목표

```
1. 전통 금융 채권 구조 그대로 온체인 재현
   - 청약(청약 기간) → 발효(이자 기산) → 쿠폰 지급 → 원금 상환
   
2. Primary Dealer 제거
   - subscribe()로 투자자가 PAR 가격에 직접 청약

3. 발행자의 실질적 자금 조달
   - 청약 대금 → 에스크로 → 발효일에 발행자 수령
   - Reserve는 조달 자금과 별도로 적립 (운용 수익으로 충당)

4. 무이표채 / 이표채 통합 설계
   - paymentSchedule[] 배열 하나로 전부 표현

5. Act/360 이자 계산 (달러 표준)
```

---

## 2. 채권 유형

### 무이표채 (Zero Coupon Bond)

```
paymentSchedule:
  [{date: 만기일, amountPerToken: 원금+할인액, isPrincipal: true}]

예시:
  maxNotional    = 10,000 USDC
  couponRateBps  = 500 (5%)
  만기            = 1년
  amountPerToken = 1,050,000 (1.05 USDC, 6 decimals)

흐름:
  투자자: 1 USDC 납입 → 토큰 1개 수령
  만기:   토큰 1개 → 1.05 USDC 수령 + 토큰 소각
```

### 이표채 (Coupon Bond)

```
paymentSchedule:
  [
    {date: 6개월, amountPerToken: 쿠폰, isPrincipal: false},
    {date: 12개월, amountPerToken: 쿠폰+원금, isPrincipal: true}
  ]

예시 (반기 지급, 연 10%):
  coupon period = 180일 (Act/360)
  couponPerToken = 1e6 × 1000 × 180 × 86400 / (360 × 86400 × 10000)
                ≈ 50,000 (0.05 USDC per token)
  finalPayment  = 1,050,000 (1.05 USDC = 원금 + 마지막 쿠폰)

흐름:
  6개월차:  claim(0) → 0.05 USDC 수령, 토큰 유지
  12개월차: claim(1) → 1.05 USDC 수령, 토큰 소각
```

### 지급 금액 계산 (Act/360, 달러 기준)

```
couponPerToken = 1e6 × couponRateBps × actualDays × 86400
                / (360 × 86400 × 10000)

               = 1e6 × couponRateBps × actualDays
                / (360 × 10000)

프론트엔드에서 계산 후 amountsPerToken 배열로 컨트랙트에 전달
컨트랙트는 전달받은 값을 그대로 사용 (재계산 없음)
```

---

## 3. 전체 라이프사이클

```
[T-n일] subscriptionStart
  → subscribe(amount) 가능
  → USDC 에스크로 보관
  → FCFS: totalSubscribed + amount ≤ maxNotional
  → 토큰 즉시 발행 (PAR 가격)

[T=0] issueDate (발효일)
  → 청약 마감
  → completeIssuance() 호출 (누구나 가능)
  → 에스크로 USDC → 발행자 지갑 (자금 조달 완료)
  → 이자 기산 시작

[T+n일, 체크포인트] paymentDate[i] - reserveBufferDays
  → checkReserveForPayment(i) 호출 가능
  → Reserve < 다음 지급액 → opsWallet 주소 공개

[T+n일, 지급일] paymentDate[i]
  → claim(i) 호출
  → isPrincipal=false: USDC 지급, 토큰 유지
  → isPrincipal=true: USDC 지급, 토큰 소각
```

---

## 4. 컨트랙트 변수

### 불변 변수 (immutable)

| 변수 | 타입 | 설명 |
|------|------|------|
| `usdc` | IERC20 | 결제 토큰 주소 |
| `opsWallet` | address | 운용 지갑 (Reserve 부족 시 공개) |
| `maxNotional` | uint256 | 최대 모집액 (USDC, 6 decimals) |
| `couponRateBps` | uint256 | 연 이율 (basis points) |
| `subscriptionStart` | uint256 | 청약 시작일 |
| `issueDate` | uint256 | 발효일 |
| `reserveBufferDays` | uint256 | Reserve 체크 버퍼 (일수) |

### 가변 변수

| 변수 | 타입 | 설명 |
|------|------|------|
| `issuer` | address | 발행자 (transferIssuer로 변경 가능) |
| `totalSubscribed` | uint256 | 실제 청약된 총액 |
| `issuanceComplete` | bool | 발행 완료 여부 |
| `reserveBalance` | uint256 | 현재 Reserve 잔액 |
| `opsWalletRevealed` | bool | 운용 지갑 공개 여부 |

### 구조체

```solidity
struct Payment {
    uint256 date;            // 지급일 (unix timestamp)
    uint256 amountPerToken;  // 토큰 1개당 USDC (6 decimals)
    bool    isPrincipal;     // true = 원금 포함, 토큰 소각
}
Payment[] public paymentSchedule;
```

### 지급 추적 매핑

| 변수 | 타입 | 설명 |
|------|------|------|
| `paymentCap[index]` | mapping(uint256→uint256) | 회차별 총 지급 상한 |
| `cumulativeClaimed[index]` | mapping(uint256→uint256) | 회차별 누적 지급액 |
| `claimed[addr][index]` | mapping(address→mapping→bool) | 주소별 청구 여부 |

---

## 5. 함수 명세

### subscribe(uint256 amount)

```
조건:
  block.timestamp >= subscriptionStart
  block.timestamp < issueDate
  !issuanceComplete
  amount > 0
  totalSubscribed < maxNotional

동작:
  actual = min(amount, remaining)  // FCFS
  usdc.safeTransferFrom(msg.sender, contract, actual)
  _mint(msg.sender, actual)        // 1:1 PAR
  subscriptions[msg.sender] += actual
  totalSubscribed += actual

이벤트: Subscribed(investor, actual)
```

### cancelSubscription()

```
조건:
  block.timestamp < issueDate
  !issuanceComplete
  subscriptions[msg.sender] > 0

동작:
  amount = subscriptions[msg.sender]
  subscriptions[msg.sender] = 0
  totalSubscribed -= amount
  _burn(msg.sender, amount)
  usdc.safeTransfer(msg.sender, amount)

이벤트: SubscriptionCancelled(investor, amount)
```

### completeIssuance()

```
조건:
  block.timestamp >= issueDate
  !issuanceComplete

동작:
  issuanceComplete = true
  usdc.safeTransfer(issuer, totalSubscribed)  // 에스크로 → 발행자

이벤트: IssuanceCompleted(totalSubscribed)
접근:   누구나 호출 가능 (발행자 안 해도 됨)
```

### reserve(uint256 amount)

```
조건:
  msg.sender == issuer
  amount > 0

동작:
  usdc.safeTransferFrom(issuer, contract, amount)
  reserveBalance += amount

이벤트: Reserved(amount, total)
```

### checkReserveForPayment(uint256 paymentIndex)

```
조건:
  block.timestamp >= paymentSchedule[paymentIndex].date - reserveBufferDays × 1 days

동작:
  required = totalSupply() × amountPerToken / 1e6
  if (reserveBalance < required && !opsWalletRevealed):
    opsWalletRevealed = true
    emit OpsWalletRevealed(opsWallet)

접근: 누구나 호출 가능
```

### claim(uint256 paymentIndex)

```
조건:
  issuanceComplete
  block.timestamp >= paymentSchedule[paymentIndex].date
  !claimed[msg.sender][paymentIndex]
  balanceOf(msg.sender) > 0

동작 (CEI 패턴):
  // 최초 호출 시 paymentCap 확정
  if paymentCap[paymentIndex] == 0:
    paymentCap[paymentIndex] = totalSupply() × amountPerToken / 1e6

  payment = tokenBalance × amountPerToken / 1e6

  // Checks
  require cumulativeClaimed + payment ≤ paymentCap
  require reserveBalance ≥ payment

  // Effects
  claimed[msg.sender][paymentIndex] = true
  cumulativeClaimed[paymentIndex] += payment
  reserveBalance -= payment
  if isPrincipal: _burn(msg.sender, tokenBalance)

  // Interactions
  usdc.safeTransfer(msg.sender, payment)

이벤트: PaymentClaimed(holder, paymentIndex, amount)
```

### withdrawExcessReserve()

```
조건:
  msg.sender == issuer

동작:
  다음 미도래 지급일 탐색
  required = totalSupply() × nextPayment.amountPerToken / 1e6
  excess = max(0, reserveBalance - required)
  require excess > 0
  reserveBalance -= excess
  usdc.safeTransfer(issuer, excess)

이벤트: ReserveWithdrawn(amount)
```

### transferIssuer(address newIssuer)

```
조건:
  msg.sender == issuer
  newIssuer != address(0)

동작:
  issuer = newIssuer

이벤트: IssuerTransferred(old, new)
```

### accruedInterestPerToken() → uint256 (view)

```
반환: 토큰 1개당 직전 지급일 이후 누적 이자 (USDC, 6 decimals)

계산:
  issuanceComplete && totalSupply() > 0 이어야 함
  lastDate = issueDate or 최근 지나간 지급일
  elapsed = block.timestamp - lastDate
  accrued = 1e6 × couponRateBps × elapsed / (360 days × 10000)

용도: 프론트엔드 Dirty Price 표시
```

---

## 6. Reserve 설계

### 기본 원칙

```
발행자는 조달 자금을 자유롭게 운용
Reserve는 각 지급일 전에 운용 수익으로 별도 충당

Reserve 최소 요건: 다음 지급 회차 금액만
  (전액 사전 적립 불필요 → 발행자 부담 최소화)
```

### 체크포인트 일정 예시 (reserveBufferDays = 7)

```
지급일 7일 전: checkReserveForPayment() 호출 가능
              Reserve 부족 → opsWallet 공개 (단 1회, 불가역)

지급일 당일:  claim() 호출 → Reserve에서 지급
지급 완료:    Reserve 소진 → 다음 체크포인트까지 요건 없음
```

---

## 7. 이중지급 방지

### 문제 상황

```
A: 1,000 토큰 보유 → claim(0) 쿠폰 수령 → 1,000 토큰을 B에게 전송
B: 1,000 토큰 보유 → claim(0) 시도 → ??
```

### 해결: paymentCap 메커니즘

```
최초 claim(0) 호출 시:
  paymentCap[0] = totalSupply() × amountPerToken / 1e6 (고정)

A 청구: cumulativeClaimed[0] = A의 몫
B 청구: cumulativeClaimed[0] + B의 몫 > paymentCap[0] → REVERT

Reserve는 paymentCap 만큼만 지급 → 이중 지급 불가
```

### 2차 시장에서의 정보 비대칭 해결

```
claimed[A][0] = true  → 온체인에서 누구나 조회 가능
cumulativeClaimed[0]  → 온체인에서 누구나 조회 가능
→ 프론트엔드: "이 회차 쿠폰은 이미 청구됨" 표시
→ 2차 시장: Clean Price로 거래 (경과이자 별도)
```

---

## 8. 경과이자

### 계산 방식

```
Act/360 (달러 표준, Money Market Convention)

직전 지급일부터 현재까지:
  accruedPerToken = 1e6 × couponRateBps × elapsed(초) / (360일(초) × 10000)

elapsed = block.timestamp - max(issueDate, lastPaymentDate)
```

### 2차 시장 Dirty Price

```
Dirty Price = Clean Price + Accrued Interest
Clean Price = 시장에서 형성되는 가격 (수익률 기준)
Accrued     = accruedInterestPerToken() 조회

→ 컨트랙트는 강제하지 않음
→ 프론트엔드에서 표시만
→ 시장 참여자가 알아서 반영
```

---

## 9. 보안 설계

| 항목 | 구현 |
|------|------|
| 재진입 공격 | ReentrancyGuard + nonReentrant |
| CEI 패턴 | burn/상태변경 → 외부호출 순서 준수 |
| transfer 안전 | SafeERC20 사용 |
| 이중 청구 | claimed[addr][index] + paymentCap |
| 악성 USDC | BondFactory 화이트리스트 |
| 채권 조건 변조 | immutable 변수 |
| 발행자 키 탈취 | transferIssuer() |
| 잉여 Reserve | withdrawExcessReserve() |
| 과거 만기일 | constructor require |
| 배열 순서 | dates ascending require |

---

## 10. BondFactory 연동

### BondParams 구조체

```solidity
struct BondParams {
    string   name;
    string   symbol;
    address  opsWallet;
    uint256  maxNotional;
    uint256  couponRateBps;
    uint256  subscriptionStart;
    uint256  issueDate;
    uint256  reserveBufferDays;
    uint256[] paymentDates;
    uint256[] amountsPerToken;
    bool[]    isPrincipal;
}
```

### createBond 호출

```javascript
// 프론트엔드에서 paymentSchedule 계산 후 전달
const schedule = computePaymentSchedule(
  issueDate, maturityDate, couponRateBps, frequency
);

await factory.createBond(USDC_ADDRESS, {
  name:              "PENNY-BOND-2026-001",
  symbol:            "PB2601",
  opsWallet:         opsWalletAddress,
  maxNotional:       parseUnits("10000", 6),
  couponRateBps:     1000,
  subscriptionStart: toUnixTimestamp("2026-06-10"),
  issueDate:         toUnixTimestamp("2026-06-20"),
  reserveBufferDays: 7,
  paymentDates:      schedule.map(p => p.date),
  amountsPerToken:   schedule.map(p => p.amount),
  isPrincipal:       schedule.map(p => p.isPrincipal),
});
```

---

## 11. 프론트엔드 연동 가이드

### 지급 스케줄 입력 UX

```
[정기 지급] 선택 시:
  주기: 월 / 분기 / 반기 / 연 선택
  → 프론트에서 자동 스케줄 생성

[커스텀] 선택 시:
  지급일: [날짜 picker]  금리: [% 입력]
  [+ 지급일 추가] 버튼으로 행 추가
  마지막 행에 자동으로 isPrincipal=true
```

### % → bps 변환

```javascript
const couponRateBps = Math.round(couponPercent * 100);
// 10% → 1000 bps
```

### amountPerToken 계산 (Act/360)

```javascript
function calcAmountPerToken(couponRateBps, fromDate, toDate) {
  const actualDays = (toDate - fromDate) / 86400;
  return Math.floor(1e6 * couponRateBps * actualDays / (360 * 10000));
}

// 마지막 지급: coupon + principal
function calcFinalAmountPerToken(couponRateBps, fromDate, toDate) {
  return 1_000_000 + calcAmountPerToken(couponRateBps, fromDate, toDate);
}
```

### 날짜 → timestamp 변환

```javascript
const maturityTs = Math.floor(new Date("2026-12-31").getTime() / 1000);
```

### 운용 지갑 링크 (Debank / Etherscan)

```javascript
const opsWallet = await bond.getOpsWallet(); // 비공개면 ZeroAddress

if (opsWallet !== ZeroAddress) {
  const debankUrl    = `https://debank.com/profile/${opsWallet}`;
  const etherscanUrl = `https://sepolia.etherscan.io/address/${opsWallet}`;
}
```

---

## 12. v2 → v3 변경사항

| 항목 | v2 | v3 |
|------|----|----|
| 채권 유형 | 고정금리 단일 만기만 | 무이표채 + 이표채 통합 |
| 청약 구조 | 없음 (즉시 발행) | subscribe/cancel/completeIssuance |
| 자금 조달 | 발행자가 Reserve 전액 적립 | 청약 대금 발행자 수령, Reserve 별도 |
| 지급 방식 | redeem() 일괄 | claim(index) 회차별 |
| 이자 계산 | 30/360 | Act/360 (달러 표준) |
| 이중지급 방지 | 없음 | paymentCap + cumulativeClaimed |
| Reserve 방식 | 전액 사전 적립 | 체크포인트 (지급 N일 전) |
| Primary Dealer | 필요 | 불필요 |
| 경과이자 | 없음 | accruedInterestPerToken() view |
| 발행자 이전 | 없음 | transferIssuer() |
