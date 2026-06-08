# EMILIO-BOND — 완전 가이드

## 개요
NFT가 채권 그 자체인 구조.
NFT를 가진 사람이 곧 청구권자이며, NFT를 양도하면 청구권도 함께 양도됩니다.

```
발행자 (호찬) → NFT 발행 → 최초 보유자
발행자 (호찬) → USDC 수시 적립
NFT 보유자    → 원할 때 claim → USDC 전액 수령
NFT 보유자    → 다른 사람에게 NFT 전송 → 청구권 양도
```

---

## 목차
1. [사전 준비](#1-사전-준비)
2. [GitHub 연동](#2-github-연동)
3. [코드 작성 및 커밋](#3-코드-작성-및-커밋)
4. [컨트랙트 배포](#4-컨트랙트-배포)
5. [나중에 다시 시작할 때](#5-나중에-다시-시작할-때)
6. [스마트 컨트랙트 사용법](#6-스마트-컨트랙트-사용법)
7. [배포 정보](#7-배포-정보)

---

## 1. 사전 준비

### MetaMask 설치 및 설정
1. Chrome → MetaMask 확장 설치
2. 지갑 생성 → **니모닉 12단어 반드시 종이에 적어서 오프라인 보관**
3. Sepolia 네트워크 추가:
   - `chainlist.org` 접속
   - 우측 상단 "Testnets" 토글 ON
   - "Sepolia" 검색 → "Add to MetaMask" 클릭
   - MetaMask 팝업 → Approve → Switch network

### Account 2 생성 (최초 수령자 역할)
1. MetaMask 상단 계정 이름 클릭
2. "Add account or hardware wallet" 클릭
3. "Add a new Ethereum account" 클릭
4. Account 2 주소 복사해서 메모장에 저장

### Sepolia ETH 받기 (가스비)
1. `cloud.google.com/application/web3/faucet/ethereum/sepolia` 접속
2. MetaMask 지갑 주소 붙여넣기
3. "Get 0.05 Sepolia ETH" 클릭
4. 하루 1회 제한 / Account 1, Account 2 각각 받기

### Sepolia USDC 받기
1. `faucet.circle.com` 접속
2. USDC 선택
3. Network: Ethereum Sepolia 선택
4. 지갑 주소 입력 → "Send 20 USDC" 클릭
5. 2시간에 1회 제한

### MetaMask에서 USDC 토큰 등록
1. MetaMask → Tokens 탭
2. 우측 상단 ⋮ → Import tokens
3. Contract address 입력:
   ```
   0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
   ```
4. Next → Import

---

## 2. GitHub 연동

### GitHub에서 repo 생성
1. `github.com` 접속 → 로그인
2. 우측 상단 `+` → "New repository" 클릭
3. Repository name 입력 (예: `emilio-bond`)
4. Private 선택
5. **"Add a README file" 체크 해제** ← 중요
6. "Create repository" 클릭

### Remix와 GitHub 연결
1. `remix.ethereum.org` 접속
2. 상단 GitHub 아이콘 클릭
3. GitHub 로그인 및 권한 승인
4. 상단에 GitHub 계정명 표시되면 성공

### Remix에서 GitHub repo Clone
1. 상단 GitHub 계정명 클릭
2. "Clone" 클릭
3. repo URL 입력:
   ```
   https://github.com/[계정명]/[repo이름]
   ```
4. Enter → 좌측 파일탐색기에 repo 폴더 생성됨

---

## 3. 코드 작성 및 커밋

### 파일 생성
좌측 파일탐색기 `+ Create` 클릭:
1. `AllowanceVault.sol`
2. `IERC20.sol`
3. `README.md`

### AllowanceVault.sol
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

contract AllowanceVault is ERC721 {

    using Strings for uint256;

    address public issuer;
    IERC20  public usdc;

    uint256 public totalMinted;
    uint256 public accumulated;
    bool    public minted;

    event Deposited(uint256 amount, uint256 total);
    event Claimed(address holder, uint256 amount);

    constructor(address _usdc)
        ERC721("EMILIO-BOND", "EMILIO")
    {
        issuer = msg.sender;
        usdc   = IERC20(_usdc);
    }

    // 토큰 이름 생성: EMILIO-BOND-001
    function tokenName(uint256 id) public pure returns (string memory) {
        string memory num;
        if (id < 10)        num = string(abi.encodePacked("00", id.toString()));
        else if (id < 100)  num = string(abi.encodePacked("0",  id.toString()));
        else                num = id.toString();
        return string(abi.encodePacked("EMILIO-BOND-", num));
    }

    // tokenURI → NFT 메타데이터
    function tokenURI(uint256 id) public pure override returns (string memory) {
        return string(abi.encodePacked(
            "data:application/json;utf8,{",
            '"name":"', tokenName(id), '",',
            '"description":"EMILIO Allowance Bond"',
            "}"
        ));
    }

    // 1. 특정 주소에게 NFT 발행
    function mintTo(address recipient) external returns (uint256) {
        require(msg.sender == issuer, "only issuer");
        require(!minted, "already minted");
        minted = true;
        totalMinted++;
        uint256 newId = totalMinted;
        _mint(recipient, newId);
        return newId;
    }

    // 2. 호찬님이 USDC 적립
    function deposit(uint256 amount) external {
        require(msg.sender == issuer, "only issuer");
        usdc.transferFrom(msg.sender, address(this), amount);
        accumulated += amount;
        emit Deposited(amount, accumulated);
    }

    // 3. NFT 소유자라면 누구든 claim
    function claim(uint256 id) external {
        require(ownerOf(id) == msg.sender, "not NFT owner");
        require(accumulated > 0, "nothing to claim");
        uint256 amount = accumulated;
        accumulated = 0;
        usdc.transfer(msg.sender, amount);
        emit Claimed(msg.sender, amount);
    }

    // 4. 잔액 확인
    function balance() external view returns (uint256) {
        return accumulated;
    }
}
```

### IERC20.sol
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}
```

### GitHub Push
1. 좌측 사이드바 Git 아이콘 클릭 (숫자 뱃지)
2. SOURCE CONTROL 펼치기
3. "Changes" 오른쪽 `+` 버튼 → 전체 stage
4. 상단 입력칸: `add contracts` 입력
5. "Commit" 버튼 클릭
6. COMMANDS 펼치기 → REMOTE 드롭다운 → origin 선택
7. "Push" 클릭
8. GitHub repo 새로고침 → 파일 확인

---

## 4. 컨트랙트 배포

### Remix 환경 설정
1. 왼쪽 사이드바 → Deploy 아이콘 클릭
2. Environment → "Browser Extension" 선택
3. 드롭다운 → "Sepolia Testnet - MetaMask" 선택
4. MetaMask 팝업 → Connect
5. Account 1 (발행자) 확인

### 컴파일
1. 상단 "Compile" 버튼 클릭
2. "Compiled" 초록불 확인

### 배포
1. Deploy 탭 → 컨트랙트 드롭다운 → `AllowanceVault` 선택
2. `_usdc` 칸 입력:
   ```
   0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
   ```
3. "Deploy" 버튼 클릭
4. MetaMask 팝업 → Confirm
5. 하단 Deployed Contracts에 주소 생성됨 → **주소 복사해서 메모**

---

## 5. 나중에 다시 시작할 때

### Remix에서 코드 가져오기
1. `remix.ethereum.org` 접속
2. 상단 GitHub 계정 연결 확인
3. GitHub 아이콘 → Clone → repo URL 입력
4. 좌측에 파일 목록 표시됨
5. AllowanceVault.sol 클릭 → Compile

### 기존 컨트랙트 불러오기
새로 배포 불필요. Add Contract로 기존 주소 불러오기:

```
Deploy 탭
→ 컨트랙트 드롭다운 → AllowanceVault 선택
→ + Add Contract → 배포된 컨트랙트 주소 입력 → OK

→ 컨트랙트 드롭다운 → IERC20 선택
→ + Add Contract
→ 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238 입력
→ OK (경고창 → OK)
```

---

## 6. 스마트 컨트랙트 사용법

### 버튼 색상
| 색상 | 의미 |
|---|---|
| 🟡 주황색 | 트랜잭션 발생 (가스비 소모) |
| 🔵 파란색 | 읽기 전용 (가스비 없음) |

### STEP 1 — USDC Approve (Account 1)
> 최초 1회. 한도 초과 시 재실행.

```
MetaMask → Account 1 확인

IERC20 컨트랙트
→ approve 🟡
→ spender: [AllowanceVault 컨트랙트 주소]
→ amount: 999999999999
→ Transact → MetaMask Confirm
```

### STEP 2 — NFT 발행 (Account 1)
> 최초 1회만 가능. EMILIO-BOND-001 발행.

```
MetaMask → Account 1 확인

AllowanceVault 컨트랙트
→ mintTo 🟡
→ recipient: [받을 사람 지갑 주소]
→ Transact → MetaMask Confirm
```

수령자 MetaMask에서 NFT 확인:
```
MetaMask → 해당 Account 전환
→ NFTs 탭 → Import NFT
→ Address: [AllowanceVault 컨트랙트 주소]
→ Token ID: 1
→ Import
```

### STEP 3 — USDC 적립 (Account 1)
> 원할 때마다 실행.

```
MetaMask → Account 1 확인

AllowanceVault 컨트랙트
→ deposit 🟡
→ amount: 5000000  (5 USDC)
→ Transact → MetaMask Confirm
```

USDC 단위 변환:
```
1 USDC   = 1000000
5 USDC   = 5000000
10 USDC  = 10000000
100 USDC = 100000000
```

### STEP 4 — 잔액 확인
```
AllowanceVault 컨트랙트
→ balance 🔵
→ Transact
→ 결과값 ÷ 1000000 = USDC 잔액
```

### STEP 5 — USDC 수령 (NFT 보유자)
> NFT 가진 사람이면 누구든 가능.

```
① MetaMask → NFT 보유 계정으로 전환
   SepoliaETH 잔액 확인 (없으면 Account 1에서 0.01 ETH 전송)

② Remix → + Add Contract
   → AllowanceVault 주소 재등록

③ AllowanceVault → claim 🟡
   → id: 1  (EMILIO-BOND-001이면 1)
   → Transact → MetaMask Confirm
```

### STEP 6 — NFT 양도 (청구권 이전)
> 엄마 → 아빠 등 청구권 양도 시.

```
MetaMask → NFT 보유 계정 전환
→ NFTs 탭 → EMILIO-BOND-001 클릭
→ Send 클릭
→ 받을 주소 입력
→ 전송 확인
```

NFT 받은 사람이 이후 claim() 호출 가능.

---

## 7. 배포 정보

```
Network          : Ethereum Sepolia (ChainID: 11155111)
AllowanceVault   : [배포 후 여기에 주소 기록]
USDC (Sepolia)   : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Issuer           : 0x914624E652DfB66edF49177d11cB7F26828f7392
```

### Etherscan 확인
```
https://sepolia.etherscan.io/address/[AllowanceVault 주소]
```

---

## 주의사항
| 상황 | 해결 |
|---|---|
| Account 전환 시 컨트랙트 사라짐 | + Add Contract로 주소 재등록 |
| deposit 실패 (allowance 에러) | IERC20 → approve 다시 실행 |
| claim 실패 (가스비 없음) | Account 1에서 해당 계정으로 0.01 ETH 전송 |
| mintTo 실패 (already minted) | 이미 발행됨, 1회만 가능 |

---

## 보안
```
공개돼도 안전한 것:
- 컨트랙트 주소
- 트랜잭션 해시
- NFT Token ID

절대 공개 금지:
- MetaMask 니모닉 12단어
- Private Key

핵심: NFT 보유자 지갑의 니모닉만 안전하면 해킹 불가.
```
