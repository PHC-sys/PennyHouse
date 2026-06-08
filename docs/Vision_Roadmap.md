# PennyHouse — 비전 & 로드맵

> 작성일: 2026-06-08  
> 목적: 프로젝트 출발점부터 장기 방향성까지 전체 맥락 기록  
> 이전 대화 및 공부 노트(HyperVault, PennyHouse 탐색) 기반 재구성

---

## 한 줄 비전

> **"누구나, 개인일지라도 자신있으면 전통 금융의 기관 역할을 대신할 수 있다는 걸 보여주는 플랫폼"**

---

## 1. 프로젝트 탄생 배경

### 1-1. 출발점: HyperVault (2026-05)

처음 시작은 **델타뉴트럴 펀딩비 캐리 Vault** 설계였다.

```
핵심 인사이트:
  델타뉴트럴 = 금리 스왑과 구조적으로 동일
  현물 매수 + Perp 숏 = Duration(델타) 헤지
  펀딩비 수취 = Floating Rate 수취 (SOFR와 동일 구조)
```

Ethena($5B TVL)가 이미 CEX 기반으로 이 전략을 증명했으나,  
**완전 온체인 + HyperEVM 특화** 버전이 없다는 공백을 발견.

당시 설계한 HyperVault 스펙:
- ETH 현물 롱 + Perp 숏 = 델타뉴트럴
- HyperLend 루프 레버리지 1.46x
- 기대 수익: 연 11.7% (펀딩비 10.95% 기준)
- V4에서 이 Vault 수익을 기반으로 고정금리 이표채 발행 계획 → **PennyHouse의 씨앗**

### 1-2. 탐색 과정 (2026-06)

```
HyperVault 설계
    ↓
예측시장 플랫폼 탐색 (Polymarket, HIP-4, PennyHouse 예측시장 컨셉)
    ↓
레버리지 예측시장 구조 설계 (KI/KO + ln(x+1) 커브)
    ↓
온체인 옵션 구현 가능성 분석 (결론: 현재 한계 명확)
    ↓
구조화채권 토크나이제이션으로 수렴
    ↓
PennyHouse = 온체인 채권 발행 플랫폼으로 확정
```

### 1-3. 핵심 결정: 왜 채권인가

- 예측시장: 유동성 문제, 헤지 수단 부재, 가격발견 불가
- 온체인 옵션: Vol Surface 유지 비용, 마진 계산 문제
- 구조화채권: **AllowanceVault(ERC-721 NFT) → StructuredBond(ERC-20)로 발전 가능**
- 기존 DeFi에 진짜 채권 발행 플랫폼이 없음 (Pendle은 기존 yield 분리일 뿐)

---

## 2. 현재까지 만든 것 (2026-06-08 기준)

### Phase 1 완료 — 온체인 채권 발행 인프라

```
AllowanceVault.sol   ERC-721 NFT 채권 원형 (학습용)
StructuredBond.sol   ERC-20 채권 토큰
  - 청약(subscribe) → 발효(completeIssuance) → 쿠폰(claim) → 원금(redeem)
  - paymentCap으로 이중지급 방지
  - Act/360 경과이자 계산 (Dirty Price 지원)
  - Reserve 체크포인트 → 부족 시 opsWallet 자동 공개
BondFactory.sol      채권 배포 공장
  - 누구나 채권 발행 가능
  - USDC 화이트리스트
테스트 45개 전부 통과
Sepolia 배포 완료
```

### Phase 2 진행 중 — 웹 프론트엔드

```
Next.js + wagmi + Tailwind (localhost:3001)
채권 목록 / 발행 폼 / 상세 대시보드
청약, Reserve 적립, 쿠폰 수령, 잉여 Reserve 회수 UI
캐시플로우 바 차트 (쿠폰=파랑, 원금=주황 스택)
투자자 예상 수령액 표시
만기 기간 표시
```

---

## 3. 신뢰 문제와 해결 방향

### 3-1. 현재 구조의 한계

지금 StructuredBond는 **발행자 신용 기반**:
```
투자자 USDC → 에스크로 → 발행자 지갑 (자유 운용)
```
발행자가 Reserve를 안 채우면 투자자 보호 불가.

### 3-2. 신뢰 3단계 로드맵

```
단계 1 (현재): 코드 신뢰
  - 컨트랙트 오픈소스 공개
  - Etherscan 검증
  - opsWallet 자동 공개 트리거

단계 2 (FundingCarryBond): 자산 신뢰
  - 발행자도 직접 인출 불가
  - 전략 컨트랙트에 자금 고정
  - 청산 트리거로 원금 보호

단계 3 (장기): 신원 신뢰
  - KYC/KYB 발행자 실명 연결
  - SPC 설립 → 법적 청구권
  - RWA 연계
```

---

## 4. 핵심 상품 로드맵

### 4-1. StructuredBond (현재) — 발행자 신용 기반 채권

누구나 채권 조건을 입력해 스마트컨트랙트를 배포하는 인프라.  
발행자 신용에 의존하지만, 투명성은 완전 온체인.

**용도**: 아는 사람끼리 사모 발행, 플랫폼 테스트

---

### 4-2. FundingCarryBond (다음) — 펀딩비 기반 고정금리 채권

> **"펀딩비가 채권 금리의 벤치마크가 되는 최초의 온체인 상품"**

```
구조:
  벤치마크 금리 = Annualized Funding Fee / 2 (델타뉴트럴이므로)
  투자자 수령   = 고정금리 (예: 연 4%)
  발행자 수익   = 초과 펀딩비 스프레드 + 레버리지 효과

신뢰 메커니즘:
  minReserve = 연 이표 × 1.2 (컨트랙트 강제)
  컨트랙트 자체가 포지션 보유 주체 (발행자도 직접 인출 불가)
  청산 트리거 = 펀딩비 수익 < 다음 이표 (Reserve 깎이는 순간)

발행자 역할:
  rebalance() → 포지션 비중 조정 (리밸런싱 Keeper)

투자자 역할:
  liquidate() → 청산 실행 (청산 Keeper, 트리거 발동 시)
```

**왜 강력한가**:
- 채권 가격 결정 근거가 생김 (펀딩비 = 오라클)
- YTM 계산 가능
- 발행자도 못 들고 튀는 구조
- HyperEVM에서만 가능 (precompile로 HL 오더북 직접 접근)

---

### 4-3. 단일 기초자산 이후 확장 전략

**FundingCarryBond ver.1** 이후 단계별 확장:

**① 멀티 자산 델타뉴트럴**
```
ETH 델타뉴트럴 + BTC 델타뉴트럴 + HYPE 델타뉴트럴
각 자산별 펀딩비를 독립적으로 수취
포트폴리오 분산으로 음수 펀딩비 리스크 완화
```

**② 크로스 에셋 롱숏 캐리**
```
BTC 롱 + ETH 숏 (펀딩비 차이 수취)
SOL 롱 + HYPE 숏
→ 두 자산 간 펀딩비 스프레드를 캐리로 수취
조건: 롱 자산 펀딩비 > 숏 자산 펀딩비
```

**③ 바스켓 캐리**
```
롱 바스켓: BTC, ETH, SAMSUNG, ...
숏 바스켓: HYNIX, SOL, XRP, ...
→ 바스켓 간 펀딩비 합산 스프레드 수취
전통 금융의 롱숏 펀드와 동일한 구조의 온체인 버전
```

---

### 4-4. GovernanceFund — 투표 기반 집단지성 펀드

> **"개인이 기관 운용에 참여하는 최초의 온체인 펀드"**

```
구조:
  투자자가 USDC 예치 → 지분 토큰 수령
  지분 가중 투표 (많이 넣을수록 더 많은 투표권)
  무투표 = 자동으로 '유지' 투표

투표 대상:
  각 자산 비중 "늘린다 / 줄인다 / 유지한다"
  BTC / ETH / USDC / 기타 자산

리밸런싱:
  투표 마감 후 rebalance() 호출 가능 (누구나, 소액 인센티브)
  컨트랙트가 HL precompile로 직접 스왑 실행
  발행자 없이 투표 결과가 곧 운용 지시

차별화:
  기존 Yearn/Beefy: 알고리즘이 운용
  GovernanceFund:   집단지성이 운용
  "내가 참여한 펀드의 성과가 내 결정으로 결정된다"
```

**내러티브**:  
민주적 자산운용. 소액 투자자도 운용 의사결정 참여 가능.

---

### 4-5. 구조화 상품 (장기) — ELS/DLS형 온체인 상품

```
원금보장형:
  USDC 90% → Aave 예치 → 만기 원금 보장
  USDC 10% → BTC 콜옵션 매수 → 상승분 일부 참여

낙인형:
  BTC가 특정 배리어 미터치 → 높은 수익률
  배리어 터치 시 → 원금 손실

레버리지 채권:
  FundingCarryBond의 레버리지 버전
```

전통 금융 ELS/DLS 구조를 온체인에서 누구나 발행 가능하게.

---

## 5. 전체 로드맵

```
Phase 1 ✅ 컨트랙트 MVP
  StructuredBond + BondFactory + 테스트 45개
  Sepolia 배포 + 실전 테스트

Phase 2 🔄 웹 프론트엔드 (진행 중)
  기본 UI 완성 (채권 목록/발행/상세/캐시플로우 차트)
  미완: cancelSubscription, checkReserveForPayment UI
  미완: Vercel 배포

Phase 3 🔜 FundingCarryBond + HyperEVM
  HyperEVM precompile 조사 (CoreWriter 0x3333...3333)
  FundingCarryStrategy 컨트랙트
    - HL Spot 현물 매수 + Perp 숏
    - 펀딩비 수취 → Reserve 자동 충전
    - 청산 트리거 + liquidate()
    - minReserve 강제
  StructuredBond에 strategyContract 옵션 추가
  claimAll() 추가 (미수령 쿠폰 일괄 수령)
  HyperEVM 배포
  프론트엔드: 펀딩비 현황, YTM, 청산 트리거 모니터링 대시보드

Phase 4 📋 GovernanceFund
  투표 컨트랙트
  리밸런싱 컨트랙트 (HL precompile 연동)
  멀티 자산 지원
  프론트엔드: 투표 UI

Phase 5 📋 전략 확장
  멀티 자산 델타뉴트럴
  크로스 에셋 롱숏 캐리
  바스켓 캐리

Phase 6 📋 구조화 상품 & 제도권
  ELS/DLS형 상품
  SPC 설립
  RWA 연계
  KYC/KYB
```

---

## 6. 플랫폼 포지셔닝

### 기존 플랫폼과의 차별점

| | Maple | Goldfinch | Pendle | Yearn | PennyHouse |
|--|--|--|--|--|--|
| 채권 발행 | ✅ | ✅ | ❌ (yield 분리) | ❌ | ✅ |
| 운용 신뢰 | 심사자 | 커뮤니티 | 코드 | 코드 | **코드 (전략 고정)** |
| 거버넌스 운용 | ❌ | ❌ | ❌ | 일부 | ✅ (Phase 4) |
| HyperEVM 특화 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 펀딩비 기반 금리 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 누구나 발행 | ❌ | ❌ | ❌ | ❌ | ✅ |

### 비어있는 포지션

> "누구나 발행 가능 + 펀딩비 기반 신뢰 + 거버넌스 참여 + HyperEVM 네이티브"

이 네 가지가 동시에 되는 플랫폼이 없음.

---

## 7. 핵심 설계 철학

**① 코드가 신뢰다**  
중개자 없이 스마트컨트랙트가 모든 규칙을 집행.  
발행자도 코드 밖으로 나갈 수 없는 구조.

**② 전통 금융 개념의 온체인 구현**  
금리 스왑 = 델타뉴트럴  
채권 = ERC-20 토큰  
쿠폰 = claim()  
YTM = 펀딩비 오라클 기반 계산  
ELS = 구조화 상품 컨트랙트

**③ 개인이 기관을 대체한다**  
채권 발행자 = 개인  
펀드 운용자 = 투표 참여자 집단  
신용 보증 = Reserve 컨트랙트

**④ 수익의 근거가 있어야 한다**  
임의의 금리가 아니라 **펀딩비**라는 시장 데이터가 기준.  
"왜 이 금리인가"에 대한 답이 온체인에 있어야 함.

---

## 8. 현재 가장 중요한 기술적 과제

**HyperEVM CoreWriter (precompile) 검증**

```
주소: 0x3333333333333333333333333333333333333333
기능: HyperEVM 컨트랙트 → HyperCore L1 오더북 주문 제출
방식: 비동기 (2-Phase Commit 패턴 필요)
검증 필요:
  - Spot 현물 매수 가능한지
  - Perp 숏 포지션 진입 가능한지
  - 펀딩비 온체인 조회 가능한지 (또는 오라클 필요한지)
참고: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/evm
```

이게 가능하면 FundingCarryBond의 핵심 인프라가 확보됨.

---

## 9. 커리어 맥락

> 한국투자증권 FICC운용부 재직 중  
> TradFi 프라이싱 + DeFi 구조 이해 + AI 활용이라는 드문 조합  
> 개발자가 될 필요 없음 — 설계/검증/판단이 역할  
> 친구들(금융공학 공부한 사람들)과 먼저 테스트, 트랙레코드 쌓고 확장

---

*이 파일은 대화와 공부 노트를 기반으로 방향성을 정리한 문서입니다.*  
*기술 스펙 상세는 docs/FundingCarryBond_spec.md 참조*  
*현재 구현 상태는 CONTEXT.md 참조*
