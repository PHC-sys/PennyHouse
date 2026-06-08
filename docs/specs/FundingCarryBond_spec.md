# FundingCarryBond — 펀딩비 기반 고정금리 채권 스펙

> 작성일: 2026-06-08  
> 최종 수정: 2026-06-08  
> 상태: 설계 확정, 구현 예정

---

## 1. 개념

델타뉴트럴 전략(현물 매수 + 무기한 선물 숏)으로 펀딩비를 수취하고,  
그 수익을 기반으로 투자자에게 **고정금리를 보장**하는 채권.

발행자는 본인 Reserve로 고정금리를 담보하고,  
운용 초과수익은 발행자가 가져가는 구조.

**핵심**: 컨트랙트 자체가 포지션 보유 주체 (발행자도 직접 인출 불가)

---

## 2. 참여자별 역할

### 투자자
- 고정금리(예: 연 4%) 채권 청약
- 원금 보장 (청산 시에도 원금 + 경과이자 수령)
- 펀딩비 변동 리스크 없음
- 청산 트리거 조건 충족 시 `liquidate()` 호출 권한

### 발행자 (운용자)
- 전략 컨트랙트 설계 및 배포
- 초기 Reserve 납입 (최소 연 이표 × 1.2 강제)
- `rebalance()` 호출로 포지션 비중 조정 (Keeper 역할)
- 운용 성과 초과분 수취
- 베이시스 리스크, 슬리피지 부담

### 컨트랙트 (FundingCarryStrategy)
- 포지션 보유 주체 (컨트랙트 주소 = HL 계정)
- HyperEVM precompile을 통해 HL Spot/Perp에 직접 주문
- 발행자도 코드 밖으로 자금 인출 불가

---

## 3. 수익 구조

```
벤치마크 금리 = Annualized Funding Fee / 2
  (델타뉴트럴 = 현물 매수 + 선물 숏 → 양방향이므로 2로 나눔)

예시 (펀딩비 연 11% 기준):
  벤치마크        = 5.5%
  투자자 쿠폰     = 4.0% (고정)
  발행자 스프레드 = 1.5% + 본인 Reserve 운용수익
```

### 자금 흐름

```
투자자 USDC (400)
발행자 Reserve (100)  ← 최소: 연 이표 × 1.2
         ↓
FundingCarryStrategy 컨트랙트 (총 500 USDC 운용)
  현물 매수 + 무기한 선물 숏 (HyperEVM precompile → HL Spot/Perp)
  펀딩비 수취 (8시간마다 숏 포지션 마진에 누적)
         ↓
  펀딩비 >= 이표  → Reserve 유지 or 증가 → 이표일에 claim()
  펀딩비 < 이표   → Reserve에서 차액 보전 → 청산 트리거 발동 가능
  운용 수익 초과분 → 발행자 수취 (withdrawExcess())
```

발행자는 본인 Reserve(100) 외에 투자자 자금(400)에도 전략 적용 →  
레버리지 효과로 추가 펀딩비 수익.

---

## 4. 최소 Reserve 요건

```
minReserve = totalNotional × couponRateBps / 10000 × 1.2

예시: 모집액 100 USDC, 연 4% 고정금리
  연 이표    = 100 × 4% = 4 USDC
  minReserve = 4 × 1.2 = 4.8 USDC
```

- 컨트랙트 배포 시 강제 검증 (미달 시 revert)
- 원금은 델타뉴트럴 포지션에 그대로 유지되므로 Reserve 커버 불필요
- Reserve는 쿠폰 지급 불능 리스크만 커버

---

## 5. 청산 트리거 설계

### 트리거 조건

**"발행자의 Reserve가 투자자를 위해 깎여야 하는 순간"** 부터 투자자가 청산 권한 획득.

구체적으로:

```
직전 이표일(또는 발효일) ~ 다음 이표일 사이 펀딩비 수익
  < 다음 이표 지급액

즉, 다음 이표를 펀딩비만으로 충당 불가 → Reserve 소진 필요
→ canLiquidate() = true
```

수식:

```
accruedFunding  = 해당 구간 펀딩비 누적 수익
nextCoupon      = totalSupply × nextAmountPerToken / 1e6

canLiquidate    = accruedFunding < nextCoupon
```

### Keeper 역할 분리

```
리밸런싱 Keeper = 발행자
  → 포지션 비중 조정 (rebalance() 호출)
  → 본인 수익을 위해 자발적 실행 동기 있음

청산 Keeper = 투자자 (canLiquidate() == true 시)
  → 본인 원금/이자 보호를 위해 자발적 실행 동기 있음
  → 누구나 호출 가능으로 열어둠 (안전망)
```

### 청산 실행

```
liquidate() 호출 시:
  1. 전략 컨트랙트 포지션 전량 청산 (HL precompile)
  2. 청산 시점까지 경과이자 계산
  3. 투자자에게 원금 + 경과이자 일괄 지급
  4. 잔여분 → 발행자 반환
```

---

## 6. 원금 보장 메커니즘

델타뉴트럴 구조에서 원금이 손실나는 시나리오:

```
현물 매수 + 선물 숏 → 가격 변동 상쇄
→ 원금 자체는 거의 그대로 유지

단, 숏 포지션 강제 청산 발생 시 (급격한 가격 상승):
  현물 평가이익 ≈ 숏 손실 (헤지 효과)
  → 포트폴리오 전체 손실 제한적
```

따라서:
- **Reserve는 쿠폰 지급 불능 리스크만 커버**
- **원금은 포지션 청산 시 자연스럽게 회수**
- 베이시스 리스크/슬리피지는 발행자 스프레드에서 부담

---

## 7. 컨트랙트 지갑 구조

```
FundingCarryStrategy 컨트랙트 주소
  = HyperEVM 주소
  = HL L1 계정 (동일 주소)

발행자가 할 수 있는 것:
  rebalance()       → 포지션 비중 조정
  withdrawExcess()  → 초과 수익만 인출 (조건 충족 시)

발행자가 할 수 없는 것:
  원금 직접 인출
  투자자 Reserve 접근
  코드 밖 자금 이동
```

### 안전장치 (ver.1)

```
EmergencyExit:
  발행자 + 투자자 과반수 동의 시 전체 청산 가능
  → 컨트랙트 버그 등 극단적 상황 대비

버그 리스크 대응:
  소액 테스트 우선 (친구들 간 테스트)
  Audit 후 실제 운용 확대
```

---

## 8. StructuredBond와의 연결

기존 StructuredBond 구조 최대한 유지.

```
현재:
  completeIssuance() → 발행자 지갑 (자유 운용)

변경:
  completeIssuance() → FundingCarryStrategy 컨트랙트 (전략 고정)
```

StructuredBond에 `strategyContract` 파라미터 추가:
- `address(0)` → 기존 방식 (발행자 지갑)
- 컨트랙트 주소 → FundingCarryStrategy로 자금 이동

### claimAll() 추가 (StructuredBond 개선)

```solidity
// 미수령 쿠폰 전체 한번에 수령 (가스비 절약)
function claimAll() external nonReentrant {
    for (uint i = 0; i < paymentSchedule.length; i++) {
        if (block.timestamp >= paymentSchedule[i].date
            && !claimed[msg.sender][i]) {
            _claim(i);
        }
    }
}
```

---

## 9. 전체 아키텍처

```
[투자자]
  USDC 납입 → subscribe()
  만기 전 이표 수령 → claimAll()
  트리거 발동 시 → liquidate()
        ↓
[StructuredBond] (ERC-20)
  청약 에스크로
  발행자 Reserve 초기 납입 (minReserve 강제)
        ↓ completeIssuance()
[FundingCarryStrategy 컨트랙트]
  현물 매수  (HL Spot, HyperEVM precompile)
  선물 숏    (HL Perp, HyperEVM precompile)
  펀딩비 수취 → 마진 잔고 누적
        ↓
  정상:    이표일에 claim() / claimAll()
  트리거:  liquidate() → 포지션 청산 → 원금+경과이자 지급
        ↑
[발행자]              [투자자]
  rebalance() 호출      canLiquidate() 확인
  (포지션 관리)          liquidate() 호출
```

---

## 10. 프론트엔드 모니터링 대시보드 (추가 예정)

```
발행자/투자자 공통:
  - 현재 펀딩비 (연환산, 8시간 기준)
  - 숏 포지션 청산 라인 (현재가 대비 %)
  - Reserve 현황 / 잔여 이표 대비 비율
  - 청산 트리거 활성화 여부 (canLiquidate)
  - 포지션 현황 (현물/선물 비중, 평가손익)
  - 누적 펀딩비 수익 vs 이표 지급액 비교
```

---

## 11. 구현 순서

```
0단계: StructuredBond 개선 (즉시)
  - claimAll() 추가

1단계: HyperEVM precompile 조사
  - HL Spot/Perp 오더북 컨트랙트 접근 가능한지 확인
  - 펀딩비 온체인 조회 가능한지 확인
  - 참고: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/evm

2단계: FundingCarryStrategy 컨트랙트
  - 현물 매수 / 선물 숏 포지션 관리
  - 펀딩비 수취 및 추적
  - rebalance(), liquidate(), withdrawExcess()
  - canLiquidate() view 함수
  - emergencyExit() (안전장치)

3단계: StructuredBond에 strategyContract 옵션 추가
  - BondParams에 strategyContract 파라미터 추가
  - completeIssuance() 분기 처리
  - minReserve 강제 검증

4단계: HyperEVM 배포 및 테스트
  - 소액으로 실제 포지션 테스트

5단계: 프론트엔드
  - 모니터링 대시보드
  - YTM 계산 및 표시
  - 청산 트리거 현황
```

---

## 12. 확장 방향

- **레버리지 전략**: 숏 포지션에 레버리지 추가 → 더 높은 수익률
- **Cross Asset 캐리**: BTC 롱 + ETH 숏 등 크로스 에셋 포지션
- **거버넌스 펀드**: 투표로 자산 비중 결정 → FundingCarry 전략의 집단지성 운용

---

## 13. 비교 우위

| | 전통 크레딧 채권 | Maple/Goldfinch | PennyHouse FundingCarry |
|--|--|--|--|
| 금리 근거 | 신용등급 | 심사자 판단 | 펀딩비 (시장 데이터) |
| 원금 보장 | 신용 의존 | 신용 의존 | 델타뉴트럴 + 청산 트리거 |
| 투명성 | 분기 공시 | 온체인 일부 | 완전 온체인 |
| 발행자 담보 | 없음 | 없음 | minReserve 강제 |
| 운용 신뢰 | 법적 계약 | 심사자 | 컨트랙트 코드 |
| HyperEVM 특화 | ❌ | ❌ | ✅ |
