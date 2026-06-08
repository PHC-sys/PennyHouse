# FundingCarryBond — 펀딩비 기반 고정금리 채권 스펙

> 작성일: 2026-06-08  
> 상태: 설계 확정, 구현 예정

---

## 1. 개념

델타뉴트럴 전략(현물 매수 + 무기한 선물 숏)으로 펀딩비를 수취하고,  
그 수익을 기반으로 투자자에게 **고정금리를 보장**하는 채권.

발행자는 본인 Reserve로 고정금리를 담보하고,  
운용 초과수익은 발행자가 가져가는 구조.

---

## 2. 참여자별 역할

### 투자자
- 고정금리(예: 연 4%) 채권 청약
- 원금 보장 (청산 시에도 원금 + 경과이자 수령)
- 펀딩비 변동 리스크 없음

### 발행자 (운용자)
- 전략 컨트랙트 설계 및 배포
- 초기 Reserve 납입 (담보 역할)
- 운용 성과 초과분 수취
- 베이시스 리스크, 슬리피지 부담

---

## 3. 수익 구조

```
벤치마크 금리 = Annualized Funding Fee / 2
  (델타뉴트럴이므로 현물+숏 양방향 → 2로 나눔)

예시 (펀딩비 연 11% 기준):
  벤치마크       = 5.5%
  투자자 쿠폰    = 4.0% (고정)
  발행자 스프레드 = 1.5% + 본인 Reserve 운용수익
```

### 자금 흐름

```
투자자 USDC (400)
발행자 Reserve (100)
         ↓
FundingCarryStrategy 컨트랙트 (총 500 USDC 운용)
  현물 매수 + 무기한 선물 숏 (HyperEVM → HL Perp/Spot)
  펀딩비 수취
         ↓
  운용 수익 중 4% → 투자자 쿠폰 (Reserve 자동 충전)
  운용 수익 초과분 → 발행자 수취
```

발행자는 본인 잔고(100) 외에 투자자 자금(400)에도 전략을 적용해  
레버리지 효과로 추가 수익을 얻음.

---

## 4. 청산 트리거 설계

### 트리거 조건

```
청산 트리거: Reserve < 원금 + 잔여쿠폰 + 버퍼

  잔여쿠폰 = totalSupply × amountPerToken × 남은 지급 횟수
  버퍼     = 원금의 N% (컨트랙트 배포 시 발행자가 설정)
```

버퍼는 슬리피지와 청산 실행 딜레이를 커버하기 위해 존재.

### 청산 실행

```
liquidate() 호출 시:
  1. 전략 컨트랙트 포지션 전량 청산
  2. 투자자에게 원금 + 해당 시점까지 경과이자 일괄 지급
  3. 잔여분은 발행자에게 반환
  4. 호출자에게 소액 인센티브 지급 (탈중앙화 Keeper 유도)
```

### 청산 실행 주체

누구나 `liquidate()` 호출 가능.  
트리거 조건 충족 시 호출자에게 소액 보상 → 자연스러운 Keeper 생태계.

---

## 5. 리스크 분담

| 리스크 | 부담 주체 | 처리 방식 |
|--------|---------|---------|
| 펀딩비 변동 | 발행자 | Reserve 버퍼로 흡수 |
| 펀딩비 음수 구간 | 발행자 | Reserve 소진 → 청산 트리거 |
| 베이시스 리스크 | 발행자 | 발행자 스프레드에서 부담 |
| 슬리피지 | 발행자 | 버퍼 설계에 반영 |
| 청산 지연 | 버퍼 | 버퍼가 딜레이 커버 |

---

## 6. StructuredBond와의 연결

기존 StructuredBond 구조를 최대한 유지하고,  
`completeIssuance()` 이후 자금 흐름만 변경.

```
현재:
  completeIssuance() → 발행자 지갑

변경:
  completeIssuance() → FundingCarryStrategy 컨트랙트
```

StructuredBond에 `strategyContract` 옵션 파라미터 추가 예정.  
`strategyContract == address(0)` 이면 기존 방식(발행자 지갑)으로 동작.

---

## 7. 전체 아키텍처

```
[투자자]
  USDC 납입 → subscribe()
        ↓
[StructuredBond] (ERC-20)
  청약 에스크로
  발행자 Reserve 초기 납입
        ↓ completeIssuance()
[FundingCarryStrategy 컨트랙트]
  현물 매수  (HL Spot, HyperEVM precompile)
  선물 숏    (HL Perp, HyperEVM precompile)
  펀딩비 수취 → Reserve 자동 적립
        ↓
  정상: Reserve → 쿠폰 지급 → claim()
  트리거 발동: liquidate() → 포지션 청산 → 원금+이자 일괄 지급
        ↑
[누구나 / Keeper]
  트리거 모니터링 → liquidate() 호출 → 소액 보상
```

---

## 8. 구현 순서

```
1단계: HyperEVM precompile 조사
  - HL Spot / Perp 오더북 컨트랙트 접근 가능한지 확인
  - 펀딩비 온체인 조회 가능한지 확인 (오라클 vs precompile)

2단계: FundingCarryStrategy 컨트랙트 설계
  - 현물 매수 / 선물 숏 포지션 관리
  - 펀딩비 수취 → Reserve 자동 충전
  - liquidate() 구현

3단계: StructuredBond에 strategyContract 옵션 추가
  - BondParams에 strategyContract 파라미터 추가
  - completeIssuance() 분기 처리

4단계: 청산 트리거 수식 확정
  - 버퍼 비율 설계
  - 잔여쿠폰 계산 로직

5단계: 프론트엔드
  - 전략 현황 (현물/선물 포지션, 펀딩비)
  - YTM 계산 및 표시
  - 청산 트리거 현황 표시
```

---

## 9. 확장 방향

- **레버리지 전략**: 숏 포지션에 레버리지 추가 → 더 높은 수익률
- **Cross Asset 캐리**: BTC 롱 + ETH 숏 등 크로스 에셋 포지션
- **거버넌스 펀드 (A 구조)**: 투표로 자산 비중 결정 → 위 전략들의 조합을 집단지성으로 운용

---

## 10. 비교 우위

| | 전통 크레딧 채권 | Maple/Goldfinch | PennyHouse FundingCarry |
|--|--|--|--|
| 금리 근거 | 신용등급 | 심사자 판단 | 펀딩비 (시장 데이터) |
| 원금 보장 | 신용 의존 | 신용 의존 | 청산 트리거 |
| 투명성 | 분기 공시 | 온체인 일부 | 완전 온체인 |
| 발행자 담보 | 없음 | 없음 | Reserve 필수 |
| HyperEVM 특화 | ❌ | ❌ | ✅ |
