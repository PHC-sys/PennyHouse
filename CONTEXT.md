# PennyHouse — 다음 Claude를 위한 컨텍스트 파일

> 이 파일은 이전 대화 내용을 요약한 것입니다.
> GitHub 코드만으로는 알 수 없는 결정 배경, 현재 상태, 다음 작업을 담고 있습니다.

---

## 1. 프로젝트 개요

**온체인 채권 발행 플랫폼.** 누구나 채권 조건을 입력하면 스마트 컨트랙트가 자동 배포되고,
청약 → 발효 → 쿠폰 지급 → 원금 상환 전 과정이 온체인에서 자동 처리됨.

**메인 타깃 체인**: HyperEVM (Hyperliquid L1)
- HL Spot 오더북(HIP-1)에 채권 토큰을 상장해 2차 시장 지원이 목표
- 현재는 Sepolia 테스트넷에서만 운영 중

---

## 2. 개발 히스토리 요약

### 컨트랙트 진화
```
v1  AllowanceVault.sol   ERC-721 NFT 채권 (학습용 원형, 현재 미사용)
v2  StructuredBond.sol   ERC-20, 고정금리, 단일 만기
v3  StructuredBond.sol   ERC-20, 청약/발효/지급스케줄, 이표채+무이표채,
(현재)                   체크포인트 Reserve, paymentCap 이중지급 방지
```

### 프론트엔드 진화
- Next.js + wagmi + Tailwind CSS로 구축
- Hydration 에러 → mounted 패턴으로 해결
- 달력 아이콘 SVG 교체 (흰색/회색 조정)
- router.push를 useEffect로 이동 (render 중 setState 에러 해결)
- 완판 시 발효일 전 발행 완료 허용 로직 추가

---

## 3. 현재 배포 상태

### Sepolia (테스트넷) — 완료
```
Network      : Ethereum Sepolia (ChainID: 11155111)
BondFactory  : 0x5baa53e4e74Bb5E51556425101a5183a9b675776
USDC         : 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
Deployer     : 0x914624E652DfB66edF49177d11cB7F26828f7392
Etherscan    : https://sepolia.etherscan.io/address/0x5baa53e4e74Bb5E51556425101a5183a9b675776
```

### HyperEVM (메인 타깃) — 미배포
```
Network      : HyperEVM (Hyperliquid L1)
BondFactory  : 미배포
USDC         : 미정 (HyperEVM USDC 주소 확인 필요)
```

### 실제 테스트 채권 (Sepolia에 존재)
```
채권명       : PENNY-BOND-2026-001 (심볼: PB2601)
발행자       : 0x9146...7392
발효일       : 2026. 6. 6.
연 이율      : 10%
총 발행액    : 10 USDC (완판)
Reserve 잔액 : 11 USDC (적립 완료)
지급 스케줄  :
  - 쿠폰   2026. 6. 7.  0.000277 USDC/토큰
  - 쿠폰   2026. 6. 8.  0.000277 USDC/토큰
  - 원금+쿠폰 2026. 6. 9.  1.000277 USDC/토큰
상태         : 발행 완료, 지급 미도래
```

---

## 4. GitHub 저장소

```
URL    : https://github.com/PHC-sys/PennyHouse.git
Branch : main
```

로컬 실행 방법:
```bash
# 컨트랙트
cd D:\DeFi\PennyHouse
npm install

# 프론트엔드
cd D:\DeFi\PennyHouse\frontend
npm install
npm run dev   # localhost:3001
```

---

## 5. 프론트엔드 구조 및 구현 상태

### 페이지
| 경로 | 파일 | 상태 | 내용 |
|------|------|------|------|
| `/` | app/page.tsx | ✅ | 채권 목록 (BondFactory.getAllBonds() 조회) |
| `/issue` | app/issue/page.tsx | ✅ | 채권 발행 폼 (BondFactory.createBond() 호출) |
| `/bond/[address]` | app/bond/[address]/page.tsx | ✅ | 채권 상세, 청약/Reserve/claim |

### 컴포넌트
| 파일 | 상태 | 내용 |
|------|------|------|
| components/Navbar.tsx | ✅ | 로고, 메뉴, MetaMask 연결/해제 |
| components/BondCard.tsx | ✅ | 홈 목록 카드 (진행바 포함) |

### lib
| 파일 | 내용 |
|------|------|
| lib/config.ts | 네트워크 설정 (Sepolia), 컨트랙트 주소 |
| lib/utils.ts | toUSDC, fromUSDC, toBps, toTimestamp, fromTimestamp, shortAddr, calcCouponPerToken, calcFinalPerToken |
| lib/BondFactoryABI.json | BondFactory ABI |
| lib/StructuredBondABI.json | StructuredBond ABI |

### 구현된 기능 (bond/[address] 페이지)
- ✅ 채권 기본 정보 조회 (이름, 발행자, 이율, 발효일, 상태)
- ✅ 총 발행액 / 청약 현황 (진행바)
- ✅ Reserve 잔액 / 경과이자 (Act/360)
- ✅ opsWallet 경고 (Reserve 부족 시만 표시)
- ✅ 지급 스케줄 테이블 (미도래/수령 버튼)
- ✅ 청약: USDC approve → subscribe 2단계
- ✅ 발행자 패널: 발행 완료 처리 버튼
- ✅ 발행자 패널: USDC approve → reserve 2단계
- ✅ Etherscan 링크
- ✅ 트랜잭션 완료 후 자동 데이터 갱신
- ✅ 캐시플로우 세로 바 차트 (쿠폰=파랑, 원금=주황 스택)
- ✅ 투자자 예상 수령액 표시 (토큰 보유자에게만)
- ✅ 만기 기간 표시 (소수점 연 단위)
- ✅ 수령 완료 상태 표시 (claimed[address][i] 온체인 조회, ✓ 수령 완료 라벨)
- ✅ 일괄 수령 버튼 (claimAll — 미수령 2건 이상 시 헤더에 노출)

## 2026-06-08 추가 설계
- 펀딩비 기반 고정금리 채권 (FundingCarryBond) 설계 확정
- 상세 스펙: `docs/specs/FundingCarryBond_spec.md`
- 거버넌스 펀드 방향성 확정 (Phase 4)
- HyperEVM precompile 조사 완료: `docs/research/HyperEVM_precompile.md` 참조
- 결론: 온체인 캐리 가능. CoreWriter 비동기 → 2-Phase Commit 패턴 필수
- 다음 최우선 작업: FundingCarryStrategy 컨트랙트 구현 (hyper-evm-lib 기반)
- 전체 비전 및 장기 로드맵: `docs/Vision_Roadmap.md` 참조

### 2026-06-08 추가 확정 내용
- minReserve = 연 이표 × 1.2 (컨트랙트 강제)
- 청산 트리거: 해당 구간 펀딩비 수익 < 다음 이표 지급액 (Reserve 깎이는 순간)
- Keeper 역할: 발행자(리밸런싱) / 투자자(청산)
- 컨트랙트 자체가 포지션 보유 주체 (발행자도 직접 인출 불가)
- 원금 별도 Reserve 불필요 (델타뉴트럴 포지션에서 자연 보존)
- claimAll() 추가 예정 (미수령 쿠폰 일괄 수령)
- ver.1은 소액 테스트 우선, Audit 후 확대

### 미구현 기능 (다음 작업 후보)
- ❌ `cancelSubscription()` 버튼 (청약 취소, 발효일 전)
- ❌ `checkReserveForPayment()` 버튼 (Reserve 체크포인트)
- ❌ 투자자의 현재 보유 토큰 수량 표시

---

## 6. 기술 스택

```
컨트랙트   : Solidity 0.8.28, Hardhat 2.28.6, OpenZeppelin 5.6.1
프론트엔드 : Next.js 16.2.7, React 19.2.4, TypeScript
Web3       : Wagmi 3.6.16, Viem 2.52.2
UI         : Tailwind CSS 4
데이터     : @tanstack/react-query 5
```

---

## 7. 핵심 설계 결정 (왜 이렇게 만들었는가)

### 무이표채가 기본 단위
이표채 = 무이표채들의 합 (Bond Stripping 이론)
→ paymentSchedule[] 배열 하나로 무이표채/이표채 통합 처리

### Reserve 체크포인트 방식
연속 적립 대신 지급일 N일 전에만 체크
→ 발행자 부담 최소화, Reserve 부족 시 opsWallet 자동 공개

### paymentCap 이중지급 방지
최초 claim 시점에 총 지급 상한 확정
→ 토큰 전송 후 이전/새 보유자 중복 청구 차단

### Primary Dealer 제거
subscribe()로 직접 청약, FCFS 방식
→ 증권사 중개 불필요

### Act/360 이자 계산
달러 채권 표준
→ accruedInterestPerToken()으로 Dirty Price 지원

---

## 8. 다음에 해야 할 작업 (우선순위 순)

### 🔴 최우선: FundingCarryBond 구현
- 설계 스펙: `docs/FundingCarryBond_spec.md`
- FundingCarryStrategy 컨트랙트 (현물+숏, 펀딩비 수취, 청산 트리거)
- StructuredBond에 strategyContract 옵션 추가

### 🟡 병행: HyperEVM 배포
```
1. hardhat.config.js 확인 (hyperEVM 네트워크 이미 설정됨)
2. HyperEVM USDC 주소 확인
3. npx hardhat run scripts/deploy.js --network hyperEVM
4. frontend/lib/config.ts에 HyperEVM 네트워크 추가
```

### 🟡 프론트엔드 미구현 기능
- `cancelSubscription()` 버튼
- `checkReserveForPayment()` 버튼

### 🟢 이후: 거버넌스 펀드 (Phase 4)
- 투표 기반 포트폴리오 운용
- FundingCarryBond 전략의 자연스러운 확장

### 🟢 Vercel 배포
- Phase 2 완료

---

## 9. 환경 설정

### .env (루트, gitignore됨)
```
PRIVATE_KEY=...          # MetaMask 개인키
SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
```

### hardhat.config.js 네트워크
```javascript
sepolia:  { url: SEPOLIA_RPC_URL, accounts: [PRIVATE_KEY] }
hyperEVM: { url: "https://rpc.hyperliquid.xyz/evm", accounts: [PRIVATE_KEY] }
```

---

## 10. 작업 방식 메모

- 유저는 한국어로 대화
- 로컬 실행 포트: 3001 (MetaMask에서 localhost:3001로 표시됨 — 정상)
- .env 파일은 로컬에만 존재, GitHub에 올리지 않음
- .env.example도 삭제함 (불필요)
- scripts/check.js: 배포 상태 확인 스크립트 (화이트리스트, 채권 수, owner 확인)
