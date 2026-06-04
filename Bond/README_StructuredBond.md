# EMILIO-STRUCTURED-BOND — 완전 가이드

## 개요
NFT가 구조화채권 그 자체인 구조.
발행 조건(Notional, Coupon, 만기 등)이 스마트컨트랙트에 하드코딩되어 있으며,
만기 도래 시 원금+이자가 자동 정산됩니다.
Reserve 지갑 잔액은 누구나 온체인에서 확인 가능하며,
Reserve가 부족하면 운용 지갑 주소가 자동으로 공개됩니다.

```
발행자        → 채권 조건 하드코딩 후 NFT 발행
발행자        → Reserve 지갑에 원금+이자 사전 적립
투자자        → NFT 매수 (청구권 취득)
컨트랙트      → 만기 도래 시 원금+이자 자동 지급
투자자        → NFT 양도 시 청구권도 함께 양도
누구나        → Reserve 잔액 실시간 확인 가능
Reserve 부족  → 운용 지갑 주소 온체인 공개
```

---

## 기존 AllowanceVault와의 차이

| 항목 | AllowanceVault | StructuredBond |
|------|----------------|----------------|
| 지급 방식 | 발행자 수시 적립 → 보유자 임의 claim | 만기 도래 시 원금+이자 자동 지급 |
| 채권 조건 | 없음 | Notional, CouponRate, MaturityDate, DayCount 하드코딩 |
| Reserve 관리 | 없음 | 최소 Reserve 강제 (다음 지급액 이상 유지) |
| 투명성 | 잔액만 공개 | Reserve 현황 + 운용지갑 조건부 공개 |
| 만기 | 없음 | 1주일 (테스트) |

---

## 목차
1. [채권 조건 (Bond Terms)](#1-채권-조건)
2. [Reserve 구조](#2-reserve-구조)
3. [컨트랙트 설계](#3-컨트랙트-설계)
4. [배포 준비](#4-배포-준비)
5. [사용법](#5-사용법)
6. [배포 정보](#6-배포-정보)

---

## 1. 채권 조건

### 테스트 스펙
```
Notional         : 100 USDC (테스트)
Coupon Rate      : 연 10% (테스트)
Maturity         : 발행일 + 7일
Day Count        : 30/360 단순화
Settlement       : USDC
쿠폰 지급        : 만기 1회 (원금 + 이자 일괄)
```

### 이자 계산
```
이자 = Notional × CouponRate × (7 / 360)
     = 100 × 0.10 × (7 / 360)
     ≈ 0.194 USDC

만기 지급액 = 100 + 0.194 ≈ 100.194 USDC
```

---

## 2. Reserve 구조

### Reserve 최소잔액 규칙
```
만기까지 남은 기간에 상관없이
Reserve ≥ 만기 지급액 (원금 + 이자) 유지

→ 발행 즉시 Reserve에 100.194 USDC 이상 예치해야 함
```

### Reserve 부족 시 트리거
```
Reserve < 만기 지급액
→ 운용 지갑 주소가 컨트랙트에 자동 공개
→ 투자자가 Etherscan에서 운용 지갑 거래내역 직접 조회 가능
```

### 지갑 구조
```
발행자 지갑 (Issuer)     : 채권 발행, Reserve 적립
Reserve 지갑             : 컨트랙트 자체 (적립금 보관)
운용 지갑 (Operations)   : 평상시 비공개, Reserve 부족 시 공개
```

---

## 3. 컨트랙트 설계

### StructuredBond.sol
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

contract StructuredBond is ERC721 {

    using Strings for uint256;

    // ── 발행자 ──────────────────────────────────────
    address public issuer;
    IERC20  public usdc;

    // ── 채권 조건 (Bond Terms) ───────────────────────
    uint256 public notional;        // 원금 (USDC 단위, 6 decimals)
    uint256 public couponRate;      // 연 이율 (basis points, 1000 = 10%)
    uint256 public issuanceDate;    // 발행일 (unix timestamp)
    uint256 public maturityDate;    // 만기일 (unix timestamp)
    uint256 public totalPayment;    // 만기 지급액 (원금 + 이자)

    // ── NFT 상태 ─────────────────────────────────────
    uint256 public totalMinted;
    bool    public bondMinted;
    bool    public settled;         // 정산 완료 여부

    // ── Reserve 투명성 ───────────────────────────────
    uint256 public reserveBalance;  // 컨트랙트 내 적립 USDC
    address public opsWallet;       // 운용 지갑 주소 (Reserve 부족 시 공개)
    bool    public opsWalletRevealed;

    // ── 이벤트 ───────────────────────────────────────
    event BondIssued(address indexed to, uint256 tokenId, uint256 maturityDate, uint256 totalPayment);
    event Reserved(uint256 amount, uint256 total);
    event Settled(address indexed holder, uint256 tokenId, uint256 amount);
    event OpsWalletRevealed(address opsWallet);

    constructor(
        address _usdc,
        address _opsWallet,
        uint256 _notional,      // e.g. 100000000 (100 USDC)
        uint256 _couponRateBps  // e.g. 1000 (10%)
    ) ERC721("EMILIO-STRUCTURED-BOND", "EMSB") {
        issuer    = msg.sender;
        usdc      = IERC20(_usdc);
        opsWallet = _opsWallet;

        notional      = _notional;
        couponRate    = _couponRateBps;
        issuanceDate  = block.timestamp;
        maturityDate  = block.timestamp + 7 days;

        // 이자 = Notional × Rate × (7/360) / 10000
        uint256 interest = (_notional * _couponRateBps * 7) / (360 * 10000);
        totalPayment = _notional + interest;
    }

    // ── 1. NFT 발행 (발행자만) ──────────────────────
    function mintBond(address recipient) external returns (uint256) {
        require(msg.sender == issuer, "only issuer");
        require(!bondMinted, "already minted");
        bondMinted = true;
        totalMinted++;
        uint256 newId = totalMinted;
        _mint(recipient, newId);
        emit BondIssued(recipient, newId, maturityDate, totalPayment);
        return newId;
    }

    // ── 2. Reserve 적립 (발행자만) ─────────────────
    function reserve(uint256 amount) external {
        require(msg.sender == issuer, "only issuer");
        usdc.transferFrom(msg.sender, address(this), amount);
        reserveBalance += amount;
        emit Reserved(amount, reserveBalance);
        _checkReserve();
    }

    // ── 3. 만기 정산 (NFT 보유자 호출) ────────────
    function settle(uint256 tokenId) external {
        require(ownerOf(tokenId) == msg.sender, "not bond holder");
        require(block.timestamp >= maturityDate, "not matured");
        require(!settled, "already settled");
        require(reserveBalance >= totalPayment, "insufficient reserve");

        settled = true;
        reserveBalance -= totalPayment;
        usdc.transfer(msg.sender, totalPayment);

        emit Settled(msg.sender, tokenId, totalPayment);
    }

    // ── 4. Reserve 부족 체크 → 운용지갑 공개 ──────
    function _checkReserve() internal {
        if (reserveBalance < totalPayment && !opsWalletRevealed) {
            opsWalletRevealed = true;
            emit OpsWalletRevealed(opsWallet);
        }
    }

    // 외부에서도 체크 가능
    function checkReserve() external {
        _checkReserve();
    }

    // ── 5. 조회 함수들 ──────────────────────────────
    function getBondTerms() external view returns (
        uint256 _notional,
        uint256 _couponRateBps,
        uint256 _issuanceDate,
        uint256 _maturityDate,
        uint256 _totalPayment,
        uint256 _daysToMaturity
    ) {
        uint256 daysLeft = 0;
        if (block.timestamp < maturityDate) {
            daysLeft = (maturityDate - block.timestamp) / 1 days;
        }
        return (
            notional,
            couponRate,
            issuanceDate,
            maturityDate,
            totalPayment,
            daysLeft
        );
    }

    function getReserveStatus() external view returns (
        uint256 _balance,
        uint256 _required,
        bool _sufficient,
        bool _opsRevealed,
        address _opsWallet
    ) {
        return (
            reserveBalance,
            totalPayment,
            reserveBalance >= totalPayment,
            opsWalletRevealed,
            opsWalletRevealed ? opsWallet : address(0)
        );
    }

    function isMatured() external view returns (bool) {
        return block.timestamp >= maturityDate;
    }

    // ── 6. tokenURI (NFT 메타데이터) ───────────────
    function tokenURI(uint256 id) public view override returns (string memory) {
        return string(abi.encodePacked(
            "data:application/json;utf8,{",
            '"name":"EMILIO-STRUCTURED-BOND-', id.toString(), '",',
            '"description":"Structured Bond | Notional: ', (notional / 1e6).toString(), ' USDC',
            ' | Maturity: 7D',
            '"}'
        ));
    }
}
```

---

## 4. 배포 준비

### 사전 준비 (기존 AllowanceVault와 동일)
- MetaMask + Sepolia 네트워크
- Sepolia ETH (가스비)
- Sepolia USDC (`0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`)

### 운용 지갑 준비
- MetaMask에서 Account 3 생성 (운용 지갑 역할)
- 주소 메모 → 배포 시 `_opsWallet` 파라미터로 입력

### 배포 파라미터
```
_usdc          : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
_opsWallet     : [Account 3 주소]
_notional      : 100000000   (100 USDC)
_couponRateBps : 1000        (연 10%)
```

---

## 5. 사용법

### STEP 1 — USDC Approve
```
IERC20 → approve
spender : [StructuredBond 컨트랙트 주소]
amount  : 999999999999
```

### STEP 2 — Reserve 적립 (발행 전에 먼저)
```
StructuredBond → reserve
amount : 100194444   (≈ 100.19 USDC, 원금+이자)
```

### STEP 3 — Reserve 상태 확인
```
StructuredBond → getReserveStatus 🔵
→ _balance   : 적립된 USDC
→ _required  : 필요한 최소 USDC (totalPayment)
→ _sufficient: true/false
→ _opsRevealed: 운용지갑 공개 여부
```

### STEP 4 — NFT 발행
```
StructuredBond → mintBond
recipient : [투자자 지갑 주소]
```

### STEP 5 — 채권 조건 확인 (투자자)
```
StructuredBond → getBondTerms 🔵
→ notional, couponRate, maturityDate, totalPayment, daysToMaturity
```

### STEP 6 — 만기 정산 (7일 후, NFT 보유자)
```
MetaMask → NFT 보유 계정 전환
StructuredBond → settle
tokenId : 1
→ totalPayment USDC 자동 수령
```

### STEP 7 — NFT 양도 (청구권 이전)
```
MetaMask → NFT 탭 → EMILIO-STRUCTURED-BOND 클릭 → Send
→ 받는 사람이 만기 시 settle() 호출 가능
```

---

## 6. 배포 정보

```
Network               : Ethereum Sepolia (ChainID: 11155111)
StructuredBond        : [배포 후 기록]
USDC (Sepolia)        : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Issuer                : 0x914624E652DfB66edF49177d11cB7F26828f7392
Ops Wallet            : [Account 3 주소 기록]
Issuance Date         : [배포일 기록]
Maturity Date         : [배포일 + 7일 기록]
Total Payment         : 100.194 USDC
```

---

## 주의사항

| 상황 | 해결 |
|------|------|
| reserve 전에 mint하면? | Reserve 부족으로 opsWallet 즉시 공개됨 → reserve 먼저 |
| settle 7일 전 호출 | "not matured" 에러 |
| Reserve 부족한데 settle | "insufficient reserve" 에러 |
| 가스비 없음 | Account 1 → 투자자 계정으로 0.01 ETH 전송 |

---

## Claude Code 작업 시 참고

기존 AllowanceVault.sol에서 확장하는 방향:
1. `accumulated` → `reserveBalance` + `totalPayment` 분리
2. `claim()` → `settle()` (만기 체크 추가)
3. `deposit()` → `reserve()` (Reserve 부족 체크 추가)
4. Bond Terms struct 추가
5. `getReserveStatus()`, `getBondTerms()` view 함수 추가
6. `opsWallet` 조건부 공개 로직 추가

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
