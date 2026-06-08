# HyperEVM Precompile & CoreWriter 기술 조사

> 작성일: 2026-06-08  
> 목적: FundingCarryBond의 온체인 델타뉴트럴 전략 구현 가능성 검토  
> 결론: **온체인 캐리 전략 구현 가능** — 단, 비동기 처리 패턴 필수

---

## 1. HyperEVM 아키텍처 개요

```
HyperCore (L1 CLOB 거래소 — Spot/Perp 오더북)
        ↑↓  동일 HyperBFT 합의
HyperEVM  (Cancun EVM — 스마트 컨트랙트 환경)
```

- HyperEVM은 독립 체인이 아니라 Hyperliquid L1의 일부
- 두 계층이 같은 합의 메커니즘을 공유 → 단일 상태
- EVM 컨트랙트는 **직전 블록의 HyperCore 상태를 읽고**, **다음 블록에 실행될 주문을 제출** 가능

**블록 구조**

| 종류 | 주기 | Gas 한도 |
|------|------|----------|
| Small block | 1초 | 2M gas |
| Big block | 60초 | 30M gas |

**네트워크 정보**

| 항목 | 값 |
|------|-----|
| Mainnet Chain ID | 999 |
| Testnet Chain ID | 998 |
| 가스 토큰 | HYPE (18 decimals) |
| EVM 스펙 | Cancun + EIP-1559 |

---

## 2. Read Precompiles (읽기) — 완전 동기, 즉시 반영

`0x0000000000000000000000000000000000000800` 시작 주소들로 HyperCore 상태를 온체인에서 직접 읽음.

### 주요 Precompile 주소

| 주소 | 기능 |
|------|------|
| `0x...0800` | 유저 Perp 포지션 (position) |
| `0x...0806` | Mark Price |
| `0x...0807` | Oracle Price |
| `0x...0808` | Spot Price |
| `0x...080a` | Perp Asset Info |
| 추가 | Spot Balance, Vault Equity, BBO, Account Margin, 펀딩비 등 |

> 전체 목록은 `hyper-evm-lib`의 `PrecompileLib.sol` 참조:  
> https://github.com/hyperliquid-dev/hyper-evm-lib

### Solidity 호출 방법

```solidity
// staticcall 직접 호출
(bool success, bytes memory result) =
    PRECOMPILE_ADDRESS.staticcall(abi.encode(perpIndex));
uint64 price = abi.decode(result, (uint64));

// L1Read.sol 상속 방식 (권장)
// hyper-evm-lib: PrecompileLib 사용
position(address user, uint32 perpIndex) → Position memory
spotBalance(address user, uint64 tokenIndex) → uint
oraclePx(uint32 perpIndex) → uint64
markPx(uint32 perpIndex) → uint64
spotPx(uint64 spotIndex) → uint64
```

### FundingCarryBond에서 사용할 함수

| 용도 | 함수 | 비고 |
|------|------|------|
| 숏 포지션 크기 확인 | `position(contractAddr, perpIndex)` | |
| 현물 보유량 확인 | `spotBalance(contractAddr, tokenIndex)` | |
| 펀딩비 조회 | `accountMarginSummary` 또는 funding precompile | 청산 트리거 계산용 |
| 마진 잔고 확인 | `accountMarginSummary(contractAddr)` | Reserve 체크용 |
| 청산가 확인 | mark price + 포지션 정보 조합 | |

---

## 3. CoreWriter (쓰기) — 비동기, 몇 초 지연

### 핵심 정보

```
주소: 0x3333333333333333333333333333333333333333
가스: 약 47,000 (25,000 burn + 나머지)
처리: 비동기 — EVM 트랜잭션 후 몇 초 뒤 HyperCore에서 실행
```

### 호출 방식

```solidity
CoreWriter(0x3333333333333333333333333333333333333333).sendRawAction(bytes data);
```

### 액션 인코딩 구조

```
[0]      : Version (현재 0x01)
[1][2][3]: Action ID (big-endian uint24)
[4...]   : ABI-encoded 파라미터
```

### 지원 Action 15종

| Action ID | 이름 | FundingCarry 관련 |
|-----------|------|-----------------|
| `0x000001` | **Limit Order** | ✅ Spot 매수 / Perp 숏 |
| `0x000006` | **Spot Send** | ✅ 자산 이동 |
| `0x000007` | **USD Class Transfer** | ✅ USDC ↔ Perp 마진 이동 |
| `0x000002` | Vault Transfer | 볼트 관리 |
| `0x00000a` | Cancel by OID | 주문 취소 |
| `0x00000b` | Cancel by CLOID | 주문 취소 |
| `0x00000d` | Send Asset | 자산 전송 |
| `0x00000f` | Borrow/Lend | 대출 |
| 나머지 7개 | 스테이킹, API 지갑 등 | - |

### Limit Order 인코딩 예시 (Perp 숏)

```solidity
// 파라미터: asset(uint32), isBuy(bool), limitPx(uint64), sz(uint64),
//           reduceOnly(bool), encodedTif(uint8), cloid(uint128)
//
// encodedTif: 1=ALO, 2=GTC, 3=IOC
// limitPx/sz: 10^8 × human readable value (예: $50,000 → 5000000000000)

bytes memory encodedAction = abi.encode(
    uint32(0),       // asset index (BTC perp = 0)
    false,           // isBuy = false → 숏
    uint64(limitPx), // 가격 × 10^8
    uint64(size),    // 수량 × 10^8
    false,           // reduceOnly
    uint8(2),        // GTC
    uint128(0)       // cloid 없음
);

bytes memory data = new bytes(4 + encodedAction.length);
data[0] = 0x01; // version
data[1] = 0x00;
data[2] = 0x00;
data[3] = 0x01; // action ID: limit order
for (uint256 i = 0; i < encodedAction.length; i++) {
    data[4 + i] = encodedAction[i];
}

CoreWriter(0x3333333333333333333333333333333333333333).sendRawAction(data);
```

### USD Class Transfer (USDC → Perp 마진)

```solidity
// Action ID 0x000007
// 파라미터: ntl(uint64 — notional), toPerp(bool)
bytes memory encodedAction = abi.encode(uint64(usdcAmount), true); // true = Spot→Perp

bytes memory data = new bytes(4 + encodedAction.length);
data[0] = 0x01;
data[1] = 0x00;
data[2] = 0x00;
data[3] = 0x07;
for (uint256 i = 0; i < encodedAction.length; i++) {
    data[4 + i] = encodedAction[i];
}
CoreWriter(0x3333333333333333333333333333333333333333).sendRawAction(data);
```

---

## 4. ⚠️ 핵심 제약사항

### 4-1. 비동기 처리 (가장 중요)

```
EVM 트랜잭션 실행 (CoreWriter.sendRawAction 호출)
        ↓  (몇 초 지연)
HyperCore 에서 주문 처리
```

- **주문 결과가 같은 트랜잭션에서 확인 불가** (원자성 없음)
- 주문 미체결 시 EVM 트랜잭션이 revert되지 않음
- → **2-Phase Commit 패턴 필수** (아래 섹션 참조)

### 4-2. 계정 사전 존재 필요

```
CoreWriter 실행 전에 해당 컨트랙트 주소(= HyperCore 계정)가
HyperCore에 이미 존재해야 함.
같은 블록에서 계정 생성 + CoreWriter 호출 불가.
```

→ 컨트랙트 배포 후 별도로 HyperCore 계정 초기화 단계 필요

### 4-3. L1 블록 내 처리 순서

```
1. L1 블록 생성
2. EVM 블록 생성
3. EVM → Core 자금 이체 처리
4. CoreWriter 액션 처리
```

### 4-4. 주문 지연 (멤풀 우회 방지)

Spot 주문 / Vault 이전은 의도적으로 몇 초 지연.  
→ 이를 이용한 프론트런 불가.

---

## 5. FundingCarryBond 구현 패턴

### 5-1. 가능/불가능 정리

| 기능 | 가능 여부 | 방법 |
|------|-----------|------|
| Spot 현물 매수 | ✅ | CoreWriter Limit Order (isBuy=true, Spot asset) |
| Perp 숏 포지션 오픈 | ✅ | CoreWriter Limit Order (isBuy=false, Perp asset) |
| USDC를 Perp 마진으로 이동 | ✅ | CoreWriter USD Class Transfer |
| 포지션 크기 읽기 | ✅ | Read precompile position() |
| 펀딩비 조회 | ✅ | Read precompile (funding rate) |
| 마진 잔고 확인 | ✅ | Read precompile accountMarginSummary() |
| 청산 트리거 판단 | ✅ | precompile 읽기 → 온체인 조건 검사 |
| 주문 즉시 실행 보장 | ❌ | 비동기 — 미체결 가능 |
| Spot 매수 + Perp 숏 원자적 동시 실행 | ❌ | 각각 별도 트랜잭션 |

### 5-2. 2-Phase Commit 패턴 (권장 구현)

```
Phase 1: 주문 제출
  completeIssuance() 호출
    → CoreWriter로 Spot 매수 주문 제출
    → CoreWriter로 Perp 숏 주문 제출
    → 상태: PENDING_OPEN
    → 타임스탬프 기록

Phase 2: 포지션 확인 (Keeper 호출)
  confirmPosition() 호출 (발행자 또는 누구나)
    → precompile로 포지션 크기 확인
    → 목표 크기에 도달했으면 상태: ACTIVE
    → 미달이면: 재시도 또는 실패 처리
    → 타임아웃 (예: 5분) 초과 시 환불 처리

이후 운용 중:
  rebalance()     → 동일한 2-phase 패턴
  liquidate()     → precompile로 조건 확인 후 포지션 청산 주문
```

### 5-3. 상태 머신

```
INACTIVE → PENDING_OPEN → ACTIVE → PENDING_CLOSE → CLOSED
              ↓ timeout                ↓ canLiquidate
           FAILED                  PENDING_CLOSE
```

---

## 6. 개발 도구

### hyper-evm-lib (공식 Foundry 라이브러리)

```bash
forge install hyperliquid-dev/hyper-evm-lib
```

- `PrecompileLib.sol`: 읽기 precompile 추상화 (EVM 주소로 토큰 인덱스 자동 조회)
- `CoreWriterLib.sol`: CoreWriter 액션 인코딩 추상화
- `TokenRegistry`: EVM 토큰 주소 ↔ HL 토큰 인덱스 매핑
- 로컬 Foundry 테스트 지원 (`vm.etch`로 precompile mock)

### 로컬 테스트 방법

```solidity
// Foundry — precompile mock
vm.etch(PRECOMPILE_ADDRESS, address(new MockPrecompile()).code);

// Hardhat
await hardhat.network.provider.send("hardhat_setCode", [
    PRECOMPILE_ADDRESS,
    mockBytecode
]);
```

---

## 7. 참고 — 유사 프로토콜 (실제 배포)

| 프로토콜 | 전략 |
|---------|------|
| **Hyperbeat** | HyperEVM 위 델타뉴트럴 메타-yield 볼트 |
| **Harmonix** | 펀딩비 기반 yield 전략 |
| **Liminal** | HyperEVM 생태계 yield |

→ 동일한 아키텍처로 실제 운용 중인 프로토콜 존재 확인.

---

## 8. 다음 단계

```
1. hyper-evm-lib 설치 (forge install)
2. FundingCarryStrategy.sol 구현
   - 2-Phase Commit 패턴
   - precompile 기반 canLiquidate() 조건
   - CoreWriter 기반 주문 실행
3. HyperEVM testnet(998)에서 포지션 테스트
4. StructuredBond에 strategyContract 옵션 연결
```

---

## 참고 문서

- [Interacting with HyperCore](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm/interacting-with-hypercore)
- [HyperEVM Overview](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperevm)
- [Interaction Timings](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm/interaction-timings)
- [hyper-evm-lib GitHub](https://github.com/hyperliquid-dev/hyper-evm-lib)
- [Demystifying Precompiles & CoreWriter](https://medium.com/@ambitlabs/demystifying-the-hyperliquid-precompiles-and-corewriter-ef4507eb17ef)
- [Read Oracle Prices — QuickNode Guide](https://www.quicknode.com/guides/hyperliquid/read-hypercore-oracle-prices-in-hyperevm)
