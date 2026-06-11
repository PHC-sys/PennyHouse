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
- HyperEVM precompile 조사 완료: `docs/research/HyperEVM_precompile.md` 참조
- 결론: 온체인 캐리 가능. CoreWriter 비동기 → 2-Phase Commit 패턴 필수
- 전체 비전 및 장기 로드맵: `docs/Vision_Roadmap.md` 참조

## ⚠️ 2026-06-10 방향 전환 — FundingCarryBond 보류, GovernanceFund 신규 착수

### FundingCarryBond → 보류

백테스트 결과 (상세: `docs/research/FundingCarryBond_backtest.md`):
- HYPE 3x는 연 17% 발행자 ROI로 경제성 확인 ✅
- BTC는 최근 펀딩비(7~8%) < 쿠폰(8%) → 발행자 구조적 손실 ❌
- 고정 쿠폰이 발행자에게 시장 리스크 집중 → 구현 보류
- 재검토 조건: 펀딩 15%+ 안정화 또는 플로팅 쿠폰 전환

### GovernanceFund → 신규 최우선

사모 거버넌스 투자 펀드. 참여자 투표로 포트폴리오 결정, AI Keeper 자동 실행.
- 본체 스펙: `docs/specs/GovernanceFund_spec.md`
- 백테스트/페이퍼 사이트 스펙: `docs/specs/GovernanceFund_Backtest_spec.md`
- 시드 투자자 확보 완료 (부장님 참여 확정)

#### 투표 → 비중 알고리즘 (검증 완료, 2026-06-10)
- 노트북: `backtest/GovernanceFund_weight_decision/01,02.ipynb`
- 검증 스크립트: `_verify_voting.py`, `_verify_engine.py` (assert 5/5 통과)
- **5단계 파이프라인**:
  1. 방향성 투표 (-2~+2, Kahoot 스타일)
  2. 예치금 가중 집계 → score(-1~+1)  [simulate_votes]
  3. 목표 비중 산출 (Target 방식, 부호=롱/숏)  [votes_to_target]
     - `target = score × vol_factor`, 정규화 `sum(abs)=100`
     - 증분 방식은 방향 전환 느려 폐기, Target 방식 채택
  4. 적응형 EMA 수렴  [adaptive_alpha]
     - `alpha = 1 - 0.1^(투표주기/T_CONVERGE)`
     - 주기 반비례 → 달력 기준 동일 반응속도 (검증됨)
  5. AI Keeper 실행 (HL REST, 지정가 추격→시장가 폴백)
- 프로파일: 공격적 T=7일/MAX 80%/5x, 보수적 T=21일/MAX 60%/2x
- 레버리지: 코인별 동일(전체 레버리지 고정), 롱/숏 양방향

#### GovernanceFund 진행 상황
1. ✅ governance_engine 모듈 추출 (노트북 → `governance/engine/*.py`)
2. ✅ 백테스트 + 페이퍼 트레이딩 사이트 (FastAPI 백엔드)
3. ✅ 데이터 레이어 확장 (캔들 페이지네이션, 펀딩비, 상대가격, interval, 신규 시나리오)
4. ✅ Next.js + Tailwind 프리미엄 프론트 재구축 (`governance/web-next`)
5. ⬜ 상업용 플랫폼 확장 → `docs/specs/GovernanceFund_Platform_roadmap.md` (← 현재)
6. ⬜ AI Keeper 프로토타입 / 온체인 컨트랙트

#### governance/ 구조 (2026-06-11 현재)
```
engine/    profiles, alpha, voting, prices, scenarios, backtest (검증된 핵심 로직)
api/       main.py(엔드포인트), paper.py(페이퍼 상태 인메모리)
web/       구버전 정적 프론트 (대체 예정, 아직 보존)
web-next/  ★ Next.js14 + Tailwind 프리미엄 프론트 (현행)
tests/     test_engine.py (assert 검증 통과)
```
실행:
- 백엔드: `python -m uvicorn governance.api.main:app --port 8099`
- 프론트: `cd governance/web-next && npm run dev` → http://localhost:3010
  (Next가 /api/* 를 8099로 프록시)

#### 상업용 플랫폼 빌드 순서 (확정, 2026-06-11)
상세: `docs/specs/GovernanceFund_Platform_roadmap.md`
```
1차: 펀딩캐리 표기 정직화 + 1x 레버리지 + 평균단가/청산가
2차: HL 전 자산(TradFi/Pre-IPO) 조회 + 변동성 자동계산 + 마켓 타일(m×n)
3차: SQLite 멀티펀드 + 펀드 개설 폼(예치금/한도/Public·Private/허용지갑/유니버스)
4차: 리플레이 모드 (게임형 과거 트레이딩)
5차: 지갑 서명 인증 (Private 펀드)
```
- **모바일 앱 확장 예정** → API-first 유지, 반응형 설계, 토큰/서명 인증
- 펀딩캐리: HL 공식 = 노셔널×펀딩레이트 (레버리지 곱 정상, 버그 아님)
- 자산: HL meta로 전 perp 제공하되 펀드는 유니버스(5~15종) 선택

#### 인프라 결정 사항 (논의 완료)
- Keeper 실행: GitHub Actions cron(주간 리밸런싱) + Render 상시서버(청산 모니터링)
- 차트 데이터: HL candleSnapshot API (검증 완료, lightweight-charts 호환)
- 배포 우선순위: 돈/컨트랙트 불필요한 백테스트·페이퍼 사이트부터

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

### 🔴 최우선: GovernanceFund MVP
- 스펙: `docs/specs/GovernanceFund_spec.md`
- AI Keeper 프로토타입 (HL REST API 연동, 가중평균 비중 → 리밸런싱)
- 웹 UI MVP (대시보드 + 투표 화면)
- 오프체인 투표 집계 (DB)

### 🟡 병행: HyperEVM 배포 (StructuredBond)
```
1. hardhat.config.js 확인 (hyperEVM 네트워크 이미 설정됨)
2. HyperEVM USDC 주소 확인
3. npx hardhat run scripts/deploy.js --network hyperEVM
4. frontend/lib/config.ts에 HyperEVM 네트워크 추가
```

### 🟡 프론트엔드 미구현 기능 (StructuredBond)
- `cancelSubscription()` 버튼
- `checkReserveForPayment()` 버튼

### 🟢 보류: FundingCarryBond 구현
- 재검토 조건 충족 시 착수: `docs/research/FundingCarryBond_backtest.md` 참조

### 🟢 Vercel 배포
- GovernanceFund MVP 완료 후

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
