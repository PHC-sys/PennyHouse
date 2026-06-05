# EMILIO-STRUCTURED-BOND — 완전 가이드

## 개요
ERC-20 토큰이 구조화채권 그 자체인 구조.
토큰을 가진 사람이 곧 청구권자이며, 토큰을 쪼개서 자유롭게 매매 가능.
만기 도래 시 보유 토큰 비례로 원금+이자가 자동 정산됩니다.
Reserve 지갑 잔액은 누구나 온체인에서 확인 가능하며,
Reserve가 부족하면 운용 지갑 주소가 자동으로 공개됩니다.

```
발행자        → 채권 조건 하드코딩 후 ERC-20 토큰 발행
발행자        → Reserve에 원금+이자 사전 적립
투자자        → 토큰 매수 (청구권 취득)
투자자        → 토큰 쪼개서 2차 시장에서 자유롭게 매매
컨트랙트      → 만기 도래 시 보유 토큰 비례로 자동 정산
누구나        → Reserve 잔액 실시간 확인 가능
Reserve 부족  → 운용 지갑 주소 온체인 자동 공개
나중에        → SPC(법인)만 붙이면 제도권 연동 가능
```

---

## 설계 원칙

### ERC-20을 선택한 이유

NFT(ERC-721)가 아닌 ERC-20으로 설계한 이유는 **유통** 때문임.

```
ERC-721 (NFT): 1장 단위 거래만 가능, 쪼개기 불가
ERC-20       : 0.001개 단위까지 자유롭게 분할 거래 가능
```

국고채처럼 사고팔려면 분할이 가능해야 함. 채권 조건(Notional, Rate, Maturity)은
토큰 안에 박는 게 아니라 컨트랙트 변수로 관리 — 이게 표준 방식.

```
토큰 1개 = 채권 1 USDC 액면 청구권
1000개 보유 = 1000 USDC 원금 청구권

만기 시:
보유 토큰 수 × (1 + 이자율) USDC 상환
토큰 burn → USDC 수령
```

### 2차 시장 (유통)

```
투자자 A: 1000 토큰 보유
→ 만기 전 600 토큰을 B에게 매도 (할인가)
→ A는 400 토큰만큼 만기 청구권 보유
→ B는 600 토큰만큼 만기 청구권 취득
→ 별도 처리 없음, 토큰 전송으로 청구권 이전 완료
```

HL Spot 오더북(HIP-1)에 올리면 실시간 YTM 형성 가능.

### 나중에 SPC만 붙이면 됨

```
지금:  발행자 지갑이 직접 Reserve 채움 (발행자 = SPC 역할)
나중:  SPC(법인) → 실제 자산 운용 수익 → Reserve 적립

바뀌는 것: Reserve를 채우는 주체
안 바뀌는 것: 컨트랙트 로직 전체
```

컨트랙트 입장에서 USDC가 어디서 왔는지 상관없음.
Ondo도 처음엔 단순한 컨트랙트로 시작, 법적 레이어는 나중에 감쌈.

---

## 기존 AllowanceVault와의 차이

| 항목 | AllowanceVault | StructuredBond |
|------|----------------|----------------|
| 토큰 표준 | ERC-721 (NFT) | ERC-20 (Fungible) |
| 분할 거래 | 불가 | 가능 (소수점 단위) |
| 지급 방식 | 보유자 임의 claim | 만기 도래 시 보유량 비례 자동 정산 |
| 채권 조건 | 없음 | Notional, CouponRate, MaturityDate 하드코딩 |
| Reserve 관리 | 없음 | 최소 Reserve 강제 |
| 투명성 | 잔액만 공개 | Reserve 현황 + 운용지갑 조건부 공개 |
| 2차 시장 | 불가 | HL Spot 오더북 상장 가능 |
| SPC 연동 | 불가 | Reserve 주체만 교체하면 됨 |

---

## 목차
1. [채권 조건 (Bond Terms)](#1-채권-조건)
2. [Reserve 구조](#2-reserve-구조)
3. [컨트랙트 설계](#3-컨트랙트-설계)
4. [배포 준비](#4-배포-준비)
5. [사용법](#5-사용법)
6. [로드맵](#6-로드맵)
7. [배포 정보](#7-배포-정보)

---

## 1. 채권 조건

### 테스트 스펙
```
Notional         : 10,000 USDC (테스트)
총 발행 토큰     : 10,000개 (1토큰 = 1 USDC 액면)
Coupon Rate      : 연 10% (테스트)
Maturity         : 발행일 + 7일
Day Count        : 30/360 단순화
Settlement       : USDC
쿠폰 지급        : 만기 1회 (원금 + 이자 일괄)
```

### 이자 계산
```
토큰 1개당 이자 = 1 USDC × 10% × (7 / 360) ≈ 0.001944 USDC
토큰 1개당 만기 지급액 ≈ 1.001944 USDC

전체 만기 지급액 = 10,000 × 1.001944 ≈ 10,019.44 USDC
```

---

## 2. Reserve 구조

### Reserve 최소잔액 규칙
```
Reserve ≥ 전체 만기 지급액 유지
= 총 발행 토큰 × 토큰당 만기 지급액
= 10,000 × 1.001944 ≈ 10,019.44 USDC

→ 발행 즉시 Reserve에 10,019.44 USDC 이상 예치
```

### Reserve 부족 시 트리거
```
Reserve < 전체 만기 지급액
→ 운용 지갑 주소가 컨트랙트에 자동 공개
→ 투자자가 Etherscan에서 운용 지갑 거래내역 직접 조회 가능
```

### 지갑 구조
```
발행자 지갑 (Issuer)     : 채권 발행, Reserve 적립 (지금은 SPC 역할 겸임)
Reserve 지갑             : 컨트랙트 자체 (USDC 보관)
운용 지갑 (Operations)   : 평상시 비공개, Reserve 부족 시 자동 공개
```

---

## 3. 컨트랙트 설계

### StructuredBond.sol (ERC-20 기반)

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract StructuredBond is ERC20 {

    // ── 발행자 ──────────────────────────────────────
    address public issuer;
    IERC20  public usdc;

    // ── 채권 조건 (Bond Terms) ───────────────────────
    uint256 public notional;        // 총 원금 (USDC, 6 decimals)
    uint256 public couponRateBps;   // 연 이율 (basis points, 1000 = 10%)
    uint256 public issuanceDate;    // 발행일 (unix timestamp)
    uint256 public maturityDate;    // 만기일 (unix timestamp)
    uint256 public paymentPerToken; // 토큰 1개당 만기 지급액 (USDC, 6 decimals)

    // ── 상태 ─────────────────────────────────────────
    bool    public settled;         // 정산 완료 여부
    uint256 public reserveBalance;  // 컨트랙트 내 적립 USDC

    // ── Reserve 투명성 ───────────────────────────────
    address public opsWallet;
    bool    public opsWalletRevealed;

    // ── 이벤트 ───────────────────────────────────────
    event BondIssued(uint256 totalSupply, uint256 maturityDate, uint256 paymentPerToken);
    event Reserved(uint256 amount, uint256 total);
    event Redeemed(address indexed holder, uint256 tokenAmount, uint256 usdcAmount);
    event OpsWalletRevealed(address opsWallet);

    constructor(
        address _usdc,
        address _opsWallet,
        uint256 _notional,      // e.g. 10000000000 (10,000 USDC, 6 decimals)
        uint256 _couponRateBps  // e.g. 1000 (10%)
    ) ERC20("EMILIO-STRUCTURED-BOND", "EMSB") {
        issuer        = msg.sender;
        usdc          = IERC20(_usdc);
        opsWallet     = _opsWallet;
        notional      = _notional;
        couponRateBps = _couponRateBps;
        issuanceDate  = block.timestamp;
        maturityDate  = block.timestamp + 7 days;

        // 토큰 1개 = 1 USDC 액면 (6 decimals)
        // 토큰 총 발행량 = notional (1:1)
        // 토큰당 이자 = 1 USDC × rate × (7/360)
        uint256 interestPerToken = (1e6 * _couponRateBps * 7) / (360 * 10000);
        paymentPerToken = 1e6 + interestPerToken;

        // 토큰 발행 (발행자에게)
        _mint(msg.sender, _notional); // 토큰 단위 = USDC 단위 (6 decimals)

        emit BondIssued(_notional, maturityDate, paymentPerToken);
    }

    // ── 1. Reserve 적립 (발행자만) ─────────────────
    function reserve(uint256 amount) external {
        require(msg.sender == issuer, "only issuer");
        usdc.transferFrom(msg.sender, address(this), amount);
        reserveBalance += amount;
        emit Reserved(amount, reserveBalance);
        _checkReserve();
    }

    // ── 2. 만기 상환 (토큰 보유자) ─────────────────
    // 보유 토큰 전량 burn → 비례 USDC 수령
    function redeem() external {
        require(block.timestamp >= maturityDate, "not matured");
        require(!settled, "already settled");

        uint256 tokenBalance = balanceOf(msg.sender);
        require(tokenBalance > 0, "no tokens");

        // 지급액 = 보유 토큰 수 × 토큰당 지급액 / 1e6
        uint256 payment = (tokenBalance * paymentPerToken) / 1e6;
        require(reserveBalance >= payment, "insufficient reserve");

        _burn(msg.sender, tokenBalance);
        reserveBalance -= payment;
        usdc.transfer(msg.sender, payment);

        // 모든 토큰 소각되면 정산 완료
        if (totalSupply() == 0) settled = true;

        emit Redeemed(msg.sender, tokenBalance, payment);
    }

    // ── 3. Reserve 부족 체크 ────────────────────────
    function _checkReserve() internal {
        uint256 required = (totalSupply() * paymentPerToken) / 1e6;
        if (reserveBalance < required && !opsWalletRevealed) {
            opsWalletRevealed = true;
            emit OpsWalletRevealed(opsWallet);
        }
    }

    function checkReserve() external { _checkReserve(); }

    // ── 4. 조회 함수들 ──────────────────────────────
    function getBondTerms() external view returns (
        uint256 _notional,
        uint256 _couponRateBps,
        uint256 _issuanceDate,
        uint256 _maturityDate,
        uint256 _paymentPerToken,
        uint256 _secondsToMaturity
    ) {
        uint256 timeLeft = block.timestamp < maturityDate
            ? maturityDate - block.timestamp : 0;
        return (notional, couponRateBps, issuanceDate, maturityDate, paymentPerToken, timeLeft);
    }

    function getReserveStatus() external view returns (
        uint256 _balance,
        uint256 _required,
        bool    _sufficient,
        bool    _opsRevealed,
        address _opsWallet
    ) {
        uint256 required = (totalSupply() * paymentPerToken) / 1e6;
        return (
            reserveBalance,
            required,
            reserveBalance >= required,
            opsWalletRevealed,
            opsWalletRevealed ? opsWallet : address(0)
        );
    }

    function isMatured() external view returns (bool) {
        return block.timestamp >= maturityDate;
    }

    // ERC-20 decimals override (USDC 맞춤)
    function decimals() public pure override returns (uint8) { return 6; }
}
```

### 핵심 변경점 (ERC-721 → ERC-20)

| 항목 | ERC-721 (구) | ERC-20 (현) |
|------|-------------|-------------|
| 토큰 표준 | NFT | Fungible |
| mintBond() | 1개 발행 | totalSupply 전량 발행 |
| settle() | tokenId 기반 | redeem() 보유량 비례 |
| 분할 거래 | 불가 | 가능 |
| 2차 시장 | OpenSea | HL Spot / DEX |

---

## 4. 배포 준비

### 사전 준비
- MetaMask + Sepolia 네트워크
- Sepolia ETH (가스비)
- Sepolia USDC (`0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`)
- Account 3 생성 (운용 지갑 역할)

### 배포 파라미터
```
_usdc          : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
_opsWallet     : [Account 3 주소]
_notional      : 10000000000   (10,000 USDC, 6 decimals)
_couponRateBps : 1000          (연 10%)
```

---

## 5. 사용법

### STEP 1 — USDC Approve (발행자)
```
IERC20 → approve
spender : [StructuredBond 컨트랙트 주소]
amount  : 999999999999
```

### STEP 2 — Reserve 적립 (발행 전에 먼저)
```
StructuredBond → reserve
amount : 10019444   (≈ 10,019.44 USDC, 원금+이자)
```

### STEP 3 — Reserve 상태 확인
```
StructuredBond → getReserveStatus 🔵
→ _balance    : 적립된 USDC
→ _required   : 필요한 최소 USDC
→ _sufficient : true/false
→ _opsRevealed: 운용지갑 공개 여부
```

### STEP 4 — 토큰 배분 (투자자에게 전송)
```
발행자 지갑 → MetaMask에서 직접 전송
받는 주소 : [투자자 지갑]
amount    : 원하는 수량 (예: 1000000 = 1,000 USDC 액면)
```

### STEP 5 — 2차 시장 거래 (투자자 간)
```
투자자 A → B에게 토큰 일부 전송 (청구권 이전)
또는 HL Spot 오더북에 올려서 매매
```

### STEP 6 — 채권 조건 확인
```
StructuredBond → getBondTerms 🔵
→ notional, couponRateBps, maturityDate, paymentPerToken, secondsToMaturity
```

### STEP 7 — 만기 상환 (7일 후, 토큰 보유자)
```
MetaMask → 토큰 보유 계정 전환
StructuredBond → redeem 🟡
→ 보유 토큰 전량 burn
→ 보유량 비례 USDC 자동 수령
```

---

## 6. 로드맵

### 지금 (테스트)
```
Sepolia 테스트넷
ERC-20 고정금리 단순 채권
발행자 지갑이 직접 Reserve 채움
```

### 다음 (실배포)
```
HyperEVM 메인넷
HL Spot 오더북(HIP-1) 상장 → 2차 시장
Factory 패턴 → 여러 시리즈 자동 배포
```

### 나중 (제도권 연동)
```
SPC(법인) 설립 → Reserve 주체 교체
실제 자산(국고채, 구조화채권) → SPC → Reserve 적립
컨트랙트 로직은 그대로
KYC/KYB → 지갑 주소 실명 매핑 공개
```

### 구조화채권 페이오프 확장
```
고정금리 → 변동금리 (오라클 연동)
Range Accrual, Inverse Floater → Chainlink/자체 오라클
한국 CD금리, KOFR → 자체 오라클 필요 (현재 Chainlink 미지원)
```

---

## 7. 배포 정보

```
Network               : Ethereum Sepolia (ChainID: 11155111)
StructuredBond        : [배포 후 기록]
USDC (Sepolia)        : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Issuer                : 0x914624E652DfB66edF49177d11cB7F26828f7392
Ops Wallet            : [Account 3 주소 기록]
Issuance Date         : [배포일 기록]
Maturity Date         : [배포일 + 7일 기록]
Total Notional        : 10,000 USDC
Payment Per Token     : ≈ 1.001944 USDC
Total Payment         : ≈ 10,019.44 USDC
```

---

## Claude Code 작업 시 참고

AllowanceVault.sol 대비 변경사항:
1. `ERC721` → `ERC20` 교체
2. `mintTo()` → constructor에서 `_mint(issuer, notional)` 전량 발행
3. `claim()` → `redeem()` (만기 체크 + 보유량 비례 + burn)
4. `deposit()` → `reserve()` (Reserve 부족 체크)
5. Bond Terms 변수 추가 (notional, couponRateBps, maturityDate, paymentPerToken)
6. `getReserveStatus()`, `getBondTerms()` view 함수
7. `decimals()` override → 6 (USDC 맞춤)

---

## 주의사항

| 상황 | 해결 |
|------|------|
| reserve 전에 배포하면? | Reserve 부족으로 opsWallet 즉시 공개 → reserve 먼저 |
| redeem 7일 전 호출 | "not matured" 에러 |
| Reserve 부족한데 redeem | "insufficient reserve" 에러 |
| 가스비 없음 | Account 1 → 투자자 계정으로 0.01 ETH 전송 |

---

## 보안

```
공개돼도 안전한 것:
- 컨트랙트 주소
- Reserve 잔액 (설계상 공개)
- Ops Wallet 주소 (Reserve 부족 시 자동 공개)

절대 공개 금지:
- MetaMask 니모닉 12단어
- Private Key
```
