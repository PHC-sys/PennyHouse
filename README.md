# PennyHouse

> 누구나 채권 계약 조건을 입력하면 스마트 컨트랙트가 자동 배포되고,  
> ERC-20 토큰이 발행되며, Vault에서 쿠폰/원금을 정산받을 수 있는  
> 온체인 채권 발행 플랫폼.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [아키텍처](#2-아키텍처)
3. [컨트랙트 구조](#3-컨트랙트-구조)
4. [개발 환경 세팅](#4-개발-환경-세팅)
5. [배포 가이드](#5-배포-가이드)
6. [로드맵](#6-로드맵)
7. [개발 일지](#7-개발-일지)
8. [배포 정보](#8-배포-정보)

---

## 1. 프로젝트 개요

### 핵심 컨셉

```
발행자  → 채권 조건 입력 (Notional, Rate, Maturity)
        → BondFactory가 개별 StructuredBond 컨트랙트 자동 배포
        → ERC-20 토큰 발행 (토큰 1개 = USDC 1 액면 청구권)
        → Reserve에 원금 + 이자 사전 적립

투자자  → 토큰 매수 (청구권 취득)
        → 소수점 단위 분할 거래 가능
        → 2차 시장 (HL Spot 오더북 / DEX) 자유 거래

만기 시 → 보유 토큰 비례로 USDC 자동 정산
        → 토큰 burn → USDC 수령
```

### 왜 ERC-20인가

국고채처럼 사고팔리려면 분할 거래가 가능해야 합니다.

| 항목 | ERC-721 (NFT) | ERC-20 (채택) |
|------|--------------|--------------|
| 분할 거래 | 불가 | 소수점 단위 가능 |
| 2차 시장 | OpenSea | HL Spot / DEX |
| 청구권 이전 | NFT 전송 | 토큰 전송 |
| 자동 정산 | 불가 | 보유량 비례 |

### Reserve 투명성

```
Reserve 잔액        → 항상 온체인 공개
Reserve 부족 발생   → 운용 지갑 주소 자동 공개
KYC/KYB 완료 시    → 지갑-실명 매핑 공개 (제도권 연동 단계)
```

### SPC 연동 (로드맵)

```
지금  : 발행자 지갑이 직접 Reserve 적립 (발행자 = SPC 역할 겸임)
나중  : SPC(법인) 설립 → 실제 자산 운용 수익 → Reserve 적립
변경점: Reserve를 채우는 주체만 교체, 컨트랙트 로직 그대로
```

Ondo Finance도 단순 컨트랙트로 시작해서 법적 레이어를 나중에 감쌌습니다.

---

## 2. 아키텍처

```
[웹 UI (Next.js)]
      ↓  wagmi / viem
[BondFactory.sol]  ← 채권 발행 공장, 주소 목록 관리
      ↓  createBond()
[StructuredBond.sol]  ← 개별 채권 컨트랙트 (ERC-20)
      ├─ reserve()   : 발행자가 USDC 사전 적립
      ├─ redeem()    : 만기 후 토큰 burn → USDC 수령
      ├─ getBondTerms()    : 채권 조건 조회
      └─ getReserveStatus(): Reserve 현황 + 운용지갑 공개 여부

[HL Spot 오더북 / DEX]  ← ERC-20 토큰 2차 시장
```

---

## 3. 컨트랙트 구조

```
contracts/
├── AllowanceVault.sol    ← v1: ERC-721 기반, 단일 NFT 채권 (원형)
├── IERC20.sol            ← USDC 인터페이스
├── StructuredBond.sol    ← v2: ERC-20 기반, 분할 가능 구조화채권
└── BondFactory.sol       ← v3: Factory 패턴, 채권 대량 배포
```

### AllowanceVault.sol (v1 — 원형)

ERC-721 NFT가 채권 그 자체인 구조. 학습 및 개념 검증용.

```
발행자 → mintTo() → NFT 발행
발행자 → deposit() → USDC 수시 적립
NFT 보유자 → claim() → USDC 전액 수령
NFT 보유자 → transfer() → 청구권 양도
```

### StructuredBond.sol (v2 — 현재 개발 중)

ERC-20으로 재설계. 채권 조건 하드코딩, Reserve 강제 관리.

```
핵심 변수:
  notional       : 총 원금 (USDC)
  couponRateBps  : 연 이율 (basis points, 1000 = 10%)
  maturityDate   : 만기일 (unix timestamp)
  paymentPerToken: 토큰 1개당 만기 지급액

핵심 함수:
  reserve()          : 발행자 USDC 적립
  redeem()           : 만기 후 토큰 burn + USDC 수령
  getBondTerms()     : 채권 조건 전체 조회
  getReserveStatus() : Reserve 현황 + 부족 시 운용지갑 공개
```

이자 계산 (30/360 단순화):
```
토큰 1개당 이자 = 1 USDC × couponRate × (만기일수 / 360)
만기 지급액     = 원금 + 이자 (토큰 보유량 비례)
```

### BondFactory.sol (v3 — 예정)

```
createBond(name, symbol, usdc, opsWallet, notional, rateBps, maturityDays)
  → StructuredBond 새 컨트랙트 자동 배포
  → allBonds[] 목록에 주소 추가
  → 발행자별 목록 관리

getAllBonds()          → 전체 채권 목록
getBondsByIssuer()    → 발행자별 채권 목록
```

---

## 4. 개발 환경 세팅

### 필수 설치

```
Cursor (또는 VS Code)
Node.js v20+
Git
MetaMask
```

### VS Code 확장

```
Solidity — Nomic Foundation
Prettier — Prettier
```

### 프로젝트 세팅

```bash
# 의존성 설치
npm install

# 환경변수 설정
cp .env.example .env
# .env 파일에 PRIVATE_KEY 입력 (MetaMask 개인키)
```

### 네트워크 설정 (hardhat.config.js)

```javascript
networks: {
  sepolia: {
    url: process.env.SEPOLIA_RPC_URL,
    accounts: [process.env.PRIVATE_KEY]
  },
  hyperEVM: {
    url: "https://rpc.hyperliquid.xyz/evm",
    accounts: [process.env.PRIVATE_KEY]
  }
}
```

---

## 5. 배포 가이드

### 테스트 전 준비

```
Sepolia ETH  : cloud.google.com/application/web3/faucet/ethereum/sepolia
Sepolia USDC : faucet.circle.com
USDC 주소    : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
```

### 컴파일 & 배포

```bash
# 컴파일
npx hardhat compile

# Sepolia 테스트 배포
npx hardhat run scripts/deploy.js --network sepolia

# 메인넷 배포 (검증 후)
npx hardhat run scripts/deploy.js --network hyperEVM
```

### 채권 발행 순서 (컨트랙트 직접 호출 시)

```
1. USDC approve  → spender: BondFactory 주소
2. createBond()  → 파라미터 입력
3. reserve()     → 원금 + 이자 사전 적립
4. 투자자에게 토큰 배분 (직접 전송 or 판매)
5. 만기 후 redeem() → 보유자가 호출 → USDC 수령
```

### EVM 호환 체인 배포

컨트랙트 코드는 변경 없음. `hardhat.config.js`에 네트워크만 추가하면 됩니다.

```
Sepolia  : 테스트
HyperEVM : 메인 타깃 (HL Spot 오더북 2차 시장 연동)
Arbitrum : 확장 가능
```

---

## 6. 로드맵

### Phase 1 — MVP (현재)

```
[x] AllowanceVault.sol — ERC-721 채권 원형 (Sepolia 배포 완료)
[ ] StructuredBond.sol — ERC-20 구조화채권
[ ] BondFactory.sol    — Factory 패턴
[ ] Sepolia 통합 테스트
```

### Phase 2 — 메인넷

```
[ ] HyperEVM 배포
[ ] HL Spot 오더북 (HIP-1) 상장 → 2차 시장
[ ] 웹 UI (Next.js + wagmi)
[ ] Reserve 대시보드 (실시간 현황)
```

### Phase 3 — 확장

```
[ ] 변동금리 (중앙화 오라클: ECOS API / FRED API → Keeper 봇)
[ ] 다중 만기 / 쿠폰 지급 스케줄
[ ] Range Accrual, Inverse Floater 등 구조화 페이오프
```

### Phase 4 — 제도권 연동

```
[ ] SPC(법인) 설립 → Reserve 주체 교체
[ ] KYC/KYB → 지갑-실명 매핑 공개
[ ] 실제 자산(국고채, 구조화채권) → SPC → Reserve 적립
[ ] 컨트랙트 로직 변경 없음
```

---

## 7. 개발 일지

학습 과정과 설계 결정 기록. `note/` 폴더 참조.

| 날짜 | 파일 | 내용 |
|------|------|------|
| 2026-05-28 | [note/20260528.md](note/20260528.md) | DeFi 기초 탐색 |
| 2026-06-01 | [note/20260601.md](note/20260601.md) | HyperVault 설계 구체화 |
| 2026-06-02 | [note/20260602(PennyHouse_Leveraged_Prediction_Market).md](note/20260602(PennyHouse_Leveraged_Prediction_Market).md) | 예측시장 레버리지 구조 탐색 |
| 2026-06-04 | [note/20260604.md](note/20260604.md) | 온체인 옵션 분석 → 구조화채권 토크나이제이션으로 수렴 |

관련 설계 문서:

| 파일 | 내용 |
|------|------|
| [note/HyperVault_Plan.md](note/HyperVault_Plan.md) | HyperVault 실행 계획 |
| [note/HyperVault_Project_Spec.md](note/HyperVault_Project_Spec.md) | HyperVault 상세 스펙 (델타뉴트럴 캐리) |
| [docs/AllowanceVault_guide.md](docs/AllowanceVault_guide.md) | AllowanceVault v1 완전 가이드 |
| [docs/StructuredBond_guide.md](docs/StructuredBond_guide.md) | StructuredBond v2 완전 가이드 |

---

## 8. 배포 정보

### AllowanceVault (v1 — Sepolia)

```
Network        : Ethereum Sepolia (ChainID: 11155111)
AllowanceVault : [배포 후 기록]
USDC (Sepolia) : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Issuer         : 0x914624E652DfB66edF49177d11cB7F26828f7392
```

### StructuredBond (v2 — Sepolia)

```
Network          : Ethereum Sepolia (ChainID: 11155111)
StructuredBond   : [배포 후 기록]
USDC (Sepolia)   : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Issuer           : 0x914624E652DfB66edF49177d11cB7F26828f7392
Ops Wallet       : [기록]
Total Notional   : 10,000 USDC (테스트)
Coupon Rate      : 연 10% (테스트)
Maturity         : 발행일 + 7일
Payment/Token    : ≈ 1.001944 USDC
```

### BondFactory (v3 — 예정)

```
Network      : Ethereum Sepolia → HyperEVM
BondFactory  : [배포 후 기록]
```

---

## 보안

```
공개돼도 안전한 것:
  컨트랙트 주소, Reserve 잔액, Ops Wallet (Reserve 부족 시)

절대 공개 금지:
  MetaMask 니모닉 12단어, Private Key
```
