# PennyHouse

> 누구나 채권 계약 조건을 입력하면 스마트 컨트랙트가 자동 배포되고,  
> 청약(Subscribe) → 발효(Issue) → 쿠폰 지급(Claim) → 원금 상환(Redeem) 전 과정이  
> 온체인에서 자동 처리되는 채권 발행 플랫폼.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [아키텍처](#2-아키텍처)
3. [컨트랙트 구조](#3-컨트랙트-구조)
4. [핵심 설계 결정](#4-핵심-설계-결정)
5. [개발 환경 세팅](#5-개발-환경-세팅)
6. [테스트](#6-테스트)
7. [배포 가이드](#7-배포-가이드)
8. [로드맵](#8-로드맵)
9. [개발 일지](#9-개발-일지)
10. [배포 정보](#10-배포-정보)

---

## 1. 프로젝트 개요

### 핵심 컨셉

```
[발행자]
  채권 조건 입력 (Notional, Rate, 지급 스케줄, 만기일)
  → BondFactory.createBond() → StructuredBond 컨트랙트 자동 배포
  → 청약 기간 설정 → 투자자 모집
  → 발효일에 자금 수령 → 운용
  → 각 지급일 전 Reserve 적립

[투자자]
  청약 기간 : subscribe() → USDC 납입 → PAR 가격으로 토큰 수령
  보유 중   : 2차 시장(HL Spot / DEX)에서 자유롭게 매매 (Dirty Price)
  지급일    : claim(index) → 쿠폰 수령 (토큰 유지)
  만기일    : claim(finalIndex) → 원금 수령 (토큰 소각)
```

### 전통 금융과의 차이

| 항목 | 전통 금융 | PennyHouse |
|------|----------|-----------|
| 발행 방식 | 증권사 중개 | 스마트 컨트랙트 직접 발행 |
| Primary Dealer | 필요 | 불필요 (subscribe()로 직접 청약) |
| 지급 정산 | T+2 결제 | 즉시 온체인 자동 정산 |
| Reserve 투명성 | 분기 공시 | 실시간 온체인 공개 |
| 경과이자 확인 | 엑셀 / KAP / 인포맥스 | 컨트랙트 view 함수 |
| 운용 지갑 추적 | 불가 | Debank / Etherscan 링크 |

---

## 2. 아키텍처

```
[웹 UI (Next.js + wagmi)]
        ↓
[BondFactory.sol]
  USDC 화이트리스트 관리
  createBond(usdc, BondParams) → StructuredBond 배포
  allBonds[], bondsByIssuer[] 목록 관리
        ↓
[StructuredBond.sol]  (ERC-20 + ReentrancyGuard)
  ├── subscribe()          청약 기간 USDC 수납 → 에스크로
  ├── cancelSubscription() 발효일 전 청약 취소 → 환불
  ├── completeIssuance()   발효일 이후 USDC → 발행자 지갑
  ├── reserve()            발행자가 지급용 USDC 적립
  ├── checkReserveForPayment() 체크포인트 도달 시 Reserve 검증
  ├── claim(index)         지급일 도래 시 쿠폰/원금 수령
  ├── withdrawExcessReserve()  잉여 Reserve 회수
  ├── transferIssuer()     발행자 주소 이전 (키 탈취 대응)
  └── accruedInterestPerToken() 경과이자 조회 (Act/360)

[HL Spot 오더북 / DEX]  ← ERC-20 토큰 2차 시장
[Debank / Etherscan]    ← 운용 지갑 트래킹 (UI 링크)
```

---

## 3. 컨트랙트 구조

```
contracts/
├── AllowanceVault.sol       ← v1: ERC-721 NFT 채권 (학습용 원형)
├── IERC20.sol               ← USDC 인터페이스
├── MockUSDC.sol             ← 테스트 전용 가짜 USDC (실배포 X)
├── StructuredBond.sol       ← v3: 현재 핵심 채권 컨트랙트
└── BondFactory.sol          ← 채권 공장 (StructuredBond 대량 배포)

test/
├── StructuredBond.test.js   ← 45개 테스트 (전체 커버)
└── BondFactory.test.js      ← Factory + E2E 테스트 포함
```

### 진화 과정

```
v1 AllowanceVault  ERC-721 NFT, 단일 청구권, 수시 적립
        ↓
v2 StructuredBond  ERC-20, 고정금리, 단일 만기, 일괄 상환
        ↓
v3 StructuredBond  ERC-20, 청약/발효/지급 스케줄, 이표채+무이표채,
(현재)             체크포인트 Reserve, 이중지급 방지(paymentCap)
```

---

## 4. 핵심 설계 결정

### 채권 유형 — 무이표채가 기본 단위

이표채는 무이표채들의 합으로 표현할 수 있습니다 (Bond Stripping 이론).

```
paymentSchedule[] 배열 하나로 통합 처리:

무이표채: [{date: 만기일, amount: 원금+할인액, isPrincipal: true}]

이표채:   [{date: 1차지급일, amount: 쿠폰,  isPrincipal: false},
           {date: 2차지급일, amount: 쿠폰,  isPrincipal: false},
           {date: 만기일,    amount: 원금+쿠폰, isPrincipal: true}]
```

### 청약(Subscribe) — Primary Dealer 제거

```
청약 기간: 투자자 USDC → 컨트랙트 에스크로 (FCFS, Notional 상한)
발효일:    에스크로 → 발행자 지갑 (실제 자금 조달)
미달 청약: 들어온 만큼만 발행 (Notional 자동 축소)
```

발행자는 조달한 자금을 자유롭게 운용하고, Reserve는 각 지급일 전에 별도로 적립합니다.

### Reserve — 체크포인트 방식

연속 적립 대신 지급일 **N일 전**에만 체크합니다.

```
체크포인트 사이: Reserve 요건 없음 (발행자 부담 최소화)
체크포인트 도달: Reserve < 다음 지급액 → opsWallet 주소 자동 공개
지급일 도달:    claim() 호출 시 Reserve에서 자동 지급
```

### 이중지급 방지 — paymentCap

토큰 전송 후 이전 보유자와 새 보유자가 같은 회차를 중복 청구하는 것을 막습니다.

```
최초 claim(index) 호출 시:
  paymentCap[index] = totalSupply × amountPerToken (확정)

이후:
  cumulativeClaimed[index] + 청구액 ≤ paymentCap[index]
  조건 위반 시 revert → 이중지급 차단
```

### 경과이자 (Dirty Price 지원)

```
Act/360 기준 (달러 표준):
  accruedInterestPerToken() = 1 USDC × rate × (직전 지급일 이후 경과초) / (360일 초)

→ 프론트엔드에서 읽어서 2차 시장 Dirty Price 표시
→ 컨트랙트는 강제하지 않음, 시장이 알아서 반영
```

### 운용 지갑 투명성

```
Reserve 충분 → opsWallet 비공개
Reserve 부족 → opsWallet 주소 온체인 공개 (자동, 불가역)

공개된 주소: Debank / Etherscan에서 실시간 자산 추적 가능
→ 분기 공시보다 더 실시간적인 투명성
```

---

## 5. 개발 환경 세팅

### 필수 설치

```
Cursor (또는 VS Code)
Node.js v20+
Git
MetaMask
```

### VS Code / Cursor 확장

```
Solidity  — Nomic Foundation  (Solidity 문법 지원)
Prettier  — Prettier          (코드 자동 정렬)
```

### 프로젝트 세팅

```bash
npm install

cp .env.example .env
# .env 에 PRIVATE_KEY 입력 (MetaMask 개인키, 0x 포함)
```

### hardhat.config.js 네트워크

```javascript
solidity: {
  version: "0.8.28",
  settings: {
    evmVersion: "cancun",
    viaIR: true,                          // 파라미터 많아서 필수
    optimizer: { enabled: true, runs: 200 }
  }
}

networks: {
  sepolia:  { url: SEPOLIA_RPC_URL, accounts: [PRIVATE_KEY] },
  hyperEVM: { url: "https://rpc.hyperliquid.xyz/evm", accounts: [PRIVATE_KEY] }
}
```

---

## 6. 테스트

```bash
npx hardhat test              # 전체 실행 (45개)
npx hardhat test --grep "청약" # 특정 케이스만
npx hardhat test test/StructuredBond.test.js  # 파일 지정
```

### 테스트 커버리지

| 영역 | 케이스 수 |
|------|---------|
| 배포 검증 (잘못된 파라미터 차단) | 4 |
| 청약 (FCFS, 취소, 기간 제한) | 6 |
| 발행 완료 (에스크로 릴리즈, Notional 축소) | 3 |
| Reserve (적립, 체크포인트, opsWallet) | 5 |
| 쿠폰 청구 (토큰 유지, 중복 방지, 소각) | 6 |
| 이중지급 방지 (paymentCap) | 2 |
| 무이표채 E2E | 2 |
| 경과이자 조회 (Act/360, 재기산) | 3 |
| 잉여 Reserve 회수 | 2 |
| 발행자 이전 | 1 |
| BondFactory (생성, 화이트리스트, 목록, E2E) | 11 |
| **합계** | **45** |

---

## 7. 배포 가이드

### 테스트 준비 (Sepolia)

```
Sepolia ETH  : cloud.google.com/application/web3/faucet/ethereum/sepolia
Sepolia USDC : faucet.circle.com
USDC 주소    : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
```

### 배포 순서

```bash
# 1. 컴파일
npx hardhat compile

# 2. Sepolia 배포
npx hardhat run scripts/deploy.js --network sepolia

# 3. 검증 후 메인넷
npx hardhat run scripts/deploy.js --network hyperEVM
```

### 채권 발행 순서 (웹 UI 기준)

```
1. BondFactory.createBond() → 채권 컨트랙트 배포
2. 청약 기간 동안 투자자 모집 (subscribe)
3. 발효일 이후 completeIssuance() → 자금 수령
4. 각 지급 체크포인트 전에 reserve() 적립
5. 지급일 도달 → 투자자가 claim(index) 호출
6. 모든 지급 완료 후 withdrawExcessReserve()
```

### EVM 호환 체인

컨트랙트 코드 변경 없이 `hardhat.config.js` 네트워크만 추가하면 됩니다.

```
Sepolia  → 테스트
HyperEVM → 메인 타깃 (HL Spot 오더북 2차 시장)
Arbitrum → 확장 가능
```

---

## 8. 로드맵

### Phase 1 — 컨트랙트 MVP ✅

```
[x] AllowanceVault.sol  ERC-721 채권 원형
[x] StructuredBond.sol  청약/발효/지급스케줄/paymentCap
[x] BondFactory.sol     USDC 화이트리스트, 채권 목록
[x] 테스트 45개 전부 통과
[x] Sepolia 배포 및 실전 테스트 완료 (2026-06-05)
```

### Phase 2 — 웹 UI ✅ (Vercel 배포 제외)

```
[x] Next.js + wagmi + viem 프론트엔드 (localhost:3001)
[x] 채권 발행 폼 (정기/커스텀 지급 스케줄)
[x] 채권 목록 / 상세 대시보드
[x] Reserve 현황 실시간 표시
[x] 운용 지갑 Debank / Etherscan 링크
[x] 경과이자 (Dirty Price) 표시
[x] 청약 / Reserve 적립 / 쿠폰·원금 수령 UI
[x] 잉여 Reserve 회수 UI
[ ] cancelSubscription UI (청약 취소)
[ ] checkReserveForPayment UI (Reserve 체크포인트)
[ ] Vercel 배포
```

### Phase 3 — 메인넷 & 2차 시장

```
[ ] HyperEVM 배포
[ ] HL Spot 오더북 (HIP-1) 상장
[ ] 유동성 부트스트래핑
```

### Phase 4 — 변동금리

```
[ ] 중앙화 오라클 (엑셀 or ECOS/FRED API → Python Keeper 봇)
[ ] couponRateBps 업데이트 함수
[ ] CD금리 / KOFR / SOFR 연동
```

### Phase 5 — 제도권 연동

```
[ ] SPC(법인) 설립 → Reserve 주체 교체
[ ] KYC/KYB → 지갑-실명 매핑 공개
[ ] 실제 자산 → SPC → Reserve 적립
```

---

## 9. 개발 일지

탐색 과정과 설계 결정 기록. `Note/` 폴더 참조.

| 날짜 | 파일 | 내용 |
|------|------|------|
| 2026-05-28 | [Note/20260528.md](Note/20260528.md) | DeFi 기초 탐색 |
| 2026-06-01 | [Note/20260601.md](Note/20260601.md) | HyperVault 설계 구체화 |
| 2026-06-02 | [Note/20260602(PennyHouse_Leveraged_Prediction_Market).md](Note/20260602(PennyHouse_Leveraged_Prediction_Market).md) | 예측시장 레버리지 구조 탐색 |
| 2026-06-04 | [Note/20260604.md](Note/20260604.md) | 온체인 옵션 분석 → 구조화채권으로 수렴 |
| 2026-06-05 | [docs/StructuredBond_v3_spec.md](docs/StructuredBond_v3_spec.md) | v3 전체 설계 확정 |
| 2026-06-05 | [CONTEXT.md](CONTEXT.md) | 프론트엔드 구현 완료, Sepolia 실전 테스트, 다음 작업 정리 |

설계 참고 문서:

| 파일 | 내용 |
|------|------|
| [Note/HyperVault_Plan.md](Note/HyperVault_Plan.md) | HyperVault 실행 계획 |
| [Note/HyperVault_Project_Spec.md](Note/HyperVault_Project_Spec.md) | 델타뉴트럴 캐리 상세 스펙 |
| [docs/AllowanceVault_guide.md](docs/AllowanceVault_guide.md) | v1 완전 가이드 |
| [docs/StructuredBond_v2_guide.md](docs/StructuredBond_v2_guide.md) | v2 설계 가이드 (역사 기록) |
| [docs/StructuredBond_v3_spec.md](docs/StructuredBond_v3_spec.md) | v3 컨트랙트 스펙 (현재) |

---

## 10. 배포 정보

### AllowanceVault (v1 — Sepolia)

```
Network        : Ethereum Sepolia (ChainID: 11155111)
AllowanceVault : [배포 후 기록]
USDC (Sepolia) : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Issuer         : 0x914624E652DfB66edF49177d11cB7F26828f7392
```

### BondFactory + StructuredBond (v3 — Sepolia)

```
Network      : Ethereum Sepolia (ChainID: 11155111)
BondFactory  : 0x5baa53e4e74Bb5E51556425101a5183a9b675776
USDC         : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Deployer     : 0x914624E652DfB66edF49177d11cB7F26828f7392
Etherscan    : https://sepolia.etherscan.io/address/0x5baa53e4e74Bb5E51556425101a5183a9b675776
```

### BondFactory + StructuredBond (v3 — HyperEVM)

```
Network      : HyperEVM (Hyperliquid L1)
BondFactory  : [배포 후 기록]
USDC         : [HyperEVM USDC 주소 기록]
```

---

## 보안

```
공개돼도 안전한 것:
  컨트랙트 주소, Reserve 잔액
  opsWallet 주소 (Reserve 부족 시 자동 공개)

절대 공개 금지:
  MetaMask 니모닉 12단어, Private Key (.env 파일)
```
