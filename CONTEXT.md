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

#### governance/ 구조 (2026-06-16 현재)
```
engine/    profiles, alpha, voting, prices, scenarios, backtest, assets (검증된 핵심 로직)
api/       main.py(엔드포인트), live.py(WS 라이브워커), store.py(SQLite),
           funds.py(펀드별 운용 엔진)   ※ 구 paper.py 제거됨
web-next/  ★ Next.js14 + Tailwind 프론트 (유일)
             app/ page(백테스트)·paper(펀드목록)·paper/[id](펀드상세)·market
             components/ Charts·TopNav·AssetModal·AssetPicker(⌘K)·CreateFundModal·useLive·useMe
tests/     test_engine.py (assert 검증 통과)
governance.db  SQLite (gitignore, 첫 실행 시 자동 생성+Demo 시드)
```
실행:
- 백엔드: `python -m uvicorn governance.api.main:app --port 8099`
- 프론트: `cd governance/web-next && npm install && npm run dev` → http://localhost:3010
  (Next가 /api/* 를 8099로 프록시)

#### 상업용 플랫폼 빌드 순서 (확정, 2026-06-11)
상세: `docs/specs/GovernanceFund_Platform_roadmap.md`
```
✅ 1차: 펀딩캐리 표기 정직화 + 1x 프로파일 + 자산별손익 + 평단/청산가
✅ 2차: HL 전 자산(265개 크립토+TradFi+Pre-IPO) + 변동성 자동 + 마켓탭
       + 상세모달 + ⌘K팔레트 + 즐겨찾기 + 거래량 + 로딩최적화(lazy/배치)
✅ 2.5차: 라이브 데이터 (HL WebSocket 워커→메모리→/ws 푸시)
        · 가격/펀딩 틱 갱신(플래시), 캔들 마지막봉 update + 봉 롤오버
        · live.py(워커), useLive.js(훅), 동적소수점 smartNum
✅ 3차: SQLite 멀티펀드 (완료)
        ✅ 3-1 store.py(SQLite) + 펀드 CRUD API (/api/funds)
        ✅ 3-2 funds.py 펀드별 운용 엔진 (유니버스/영속/라이브평가)
        ✅ 3-3 펀드 목록 + 개설 폼(탭/⌘K 유니버스) + 상세 화면
        ✅ 3-4 현금(Cash) 투표 + 라이브 NAV(분단위 영속)
            + 자산별 레버리지 캡/청산가(가격)/결제통화(USDC·USDH)/펀딩캐시
        ✅ 정리: 구 단일 paper.py·정적 web/ 제거, 차트 시간축(timeVisible)
✅ 3.5차: 운영 보강 (2026-06-15)
        ✅ 라이브 워커 전 dex 동적 구독 (km/flx 등 자산 평단·청산가 누락 버그 수정)
        ✅ Pre-IPO/상장폐지 자산 settle-to-cash (보유 자산 delist 시 최종가 청산→현금)
        ✅ 참가자 지분 회수(redeem) — share만큼 인출 + 투표 삭제(영속)
        ✅ 펀드 삭제 게이트 — 생성자 + 자금 0일 때만 (프론트 버튼 신규)
        ✅ 펀드 목록 "내 펀드" 탭 (creator===me)
        ✅ 런타임 스냅샷 영속화 — equity/비중/손익/평단을 fund_runtime(SQLite)에
           저장·복원 → 백엔드 재시작해도 라이브 테스트 유지 (전엔 메모리라 리셋됐음)
⬜ 4차: 리플레이 모드 (게임형 과거 트레이딩) ← 다음 후보
⬜ 5차: 지갑 서명 인증 (Private 펀드)
⬜ 6차: 운영자 어드민 (초대제/가입 승인제)
```

#### ★ 다음 세션에서 정할 것 (2026-06-15 갱신)
```
1) Pre-IPO 자산 생애주기  ✅ 해결 (2026-06-15)
   - 실측: HL은 isDelisted 플래그만 줌. delisting '사유'도 '후속 종목 링크'도 없음.
     · vntl:SPACEX = 진짜 delisted, vntl:BIOTECH = vol0이지만 정상 (둘은 별개)
     · vntl:GOLDJM/SILVERJM도 delisted → delisting은 IPO 전용 이벤트가 아님(원자재 계약 교체)
   - 결론: "IPO 전환 자동 감지"는 데이터상 불가 → 풀 수 있는 건 '보유 포지션 정산'.
   - 채택: settle-to-cash — delist 시 최종 mark로 청산→현금, 비중0, 손익동결, "정산됨" 표시.
     (실제 HL이 perp delist 시 미결제 포지션을 최종 mark로 강제정산하는 것과 동일)
   - 후속종목 매핑: assets.PREIPO_SUCCESSOR 훅만 마련(현재 빈 dict). 실제 후속 상장주가
     HL에 생기면 한 줄 추가로 롤오버 활성화, 없으면 cash 폴백.

2) 자산 분류 vs HL 일치 문제  ⬜ 여전히 열림
   - HL API엔 카테고리 필드 없음 → 키워드(_classify)로 복제 중 → 빈틈 생김
   - 옵션: A) 키워드 정교화  B) dex 기반 대분류  C) 검색에 회사명 별칭(SpaceX→SPCX)
   - "SPACE" 검색이 "SPCX"(티커) 못 찾는 문제도 여기 포함

3) 거래량 0(죽은 마켓) 자산 처리  ✅ 사실상 해소
   - 발견 목록은 이미 isDelisted 기준이라 vol0(BIOTECH 등)은 정상 유지 = 맞는 동작.
   - 실제로 빼야 하는 건 delisted뿐 → 1)의 settle-to-cash로 커버됨.

→ 다음 할 일: 2번(분류/검색 별칭) 마무리 or 4차 리플레이 착수.
```

#### ★ 핵심 설계 통찰 — DB(페이퍼) vs 블록체인(실제)
```
SQLite/계산은 "지갑 없는 페이퍼/테스트"를 위한 것.
실제 펀드(EVM)에서는 계산이 아니라 '펀드 지갑 포지션을 읽음':
  포지션/평단(entryPx)/손익(unrealizedPnl)/청산가(liquidationPx)/펀딩 = HL API 읽기
→ 실제는 지갑이 '진실의 원천' → 서버 다운/재시작과 무관 (자산 온체인).

[페이퍼(지금)]  지갑 없음 → 서버가 가상 계산. 런타임 상태(equity/평단/손익)는
               이제 fund_runtime(SQLite)에 스냅샷 영속 → 재시작해도 복원
               (2026-06-15. 전엔 메모리라 재시작 시 리셋됐음. 투표/메타/NAV는 원래 생존).
               저장은 _mark_to_market에서 쓰로틀(8s)+투표/회수 직후 강제.
[실제(5차+)]   지갑이 DB. 서버는 읽어서 표시만. "서버 죽으면?" 질문 자체 소멸.
둘은 공존: 페이퍼/데모(DB) = 체험·테스트, 실제 펀드(블록체인) = 운용.
같은 엔진(votes_to_target) 재사용. DB는 GitHub에 안 올림(*.db gitignore,
코드가 init_db로 자동 생성 + Demo 펀드 시드).
```

#### 3-4에서 반영할 설계 결정 (2026-06-11 논의)
```
1) Cash(현금) 항목 + "정리(Close)" 투표  ★채택
   - 투표 방향을 6개로: 강숏/숏/유지/롱/강롱 + [정리]
   - "정리"=그 종목 target 0 → 빠진 비중은 CASH로
   - Cash 비중 = 100 - sum(abs(active)). gross exposure < 100% 허용
     (지금은 항상 100% 풀투자 → 정리 허용 시 현금 보유 가능)
   - Cash 행: 펀딩 없음/평가손익 없음/안전. 실제 펀드의 USDC 보유와 일치
   - "방향 모를 때 현금" 표현 가능

2) 개인 "정리"의 한계 = 거버넌스 본질 (버그 아님)
   - 여러 명 투표 시 가중평균이라 한 명이 정리해도 0이 안 됨 → 정상
   - 개인 정리(=내가 빠지고싶다)는 비중이 아니라 '출금(redeem)' 문제
   - 출금/탈퇴는 별도 기능(지분 회수) — 3차 후반 or 나중. 비중과 분리.
   - UX: "내 투표 vs 집단 결과" 명확히 표시
   - (운영자 emergencyExit 전체정리는 컨트랙트 단계에서)

3) NAV 라이브 + 저장 최소화
   - 화면: 분봉 차트처럼 현재 점만 5초 실시간으로 흐르게
   - 평가손익 = 진입가 대비 현재가 (페이퍼. 실제는 지갑 unrealizedPnl 읽기)
   - 저장 부담: NAV 시계열 통째 저장 X → "포지션 변경 이력 + HL 가격"으로
     언제든 재구성. 실제(온체인)에선 거래이력만 있으면 NAV 재계산 가능
     → DB/블록체인에 NAV 수천 점 저장 불필요
```

#### 멀티펀드 백엔드 구조 (3-1·3-2)
```
api/store.py  SQLite: funds/votes/nav_history/allowlist (영속)
api/funds.py  fund_id별 런타임 상태(메모리) + 펀드 유니버스 운용
              · mark-to-market은 live 워커 메모리에서 (REST X)
              · 메타/펀딩/레버리지는 fetch_universe 레지스트리(HIP-3 포함)
펀드 필드: kind(demo|real), visibility(public|private), creator(닉네임=localStorage),
          universe[], profile/leverage, initial_deposit, max_deposit, allowlist(저장만)
API: POST/GET /api/funds, GET /api/funds/{id},
     /api/funds/{id}/vote · /state · /reset · /redeem(지분 회수)
     DELETE /api/funds/{id}?user= — 생성자 + 자금 0일 때만 (가드)
상장폐지: assets.delisted_map(보유 자산 정산용) + PREIPO_SUCCESSOR(후속종목 매핑 훅).
  funds.py가 보유 자산 delist 감지→settle-to-cash(비중0/손익동결/현금). state에 settled 플래그.
회수(redeem): share만큼 equity/initial/asset_pnl 동일비율 축소(남은 참가자 가치 불변),
  투표는 store.delete_vote로 영속 삭제. 전원 회수 시 자본 0 → 생성자 삭제 가능.
  (실주문 연동 전 페이퍼 인출 — 자본 차감은 런타임 메모리, 투표 삭제는 SQLite)
목록 정렬: 내펀드(creator/투표) → demo → 최신. 첫실행 Demo펀드 자동시드.
멀티유저 식별: 인증(5차) 전까지 localStorage 닉네임(useMe).
현금: 투표에 cash(0~100), 종목 target을 (100-cash)로 스케일. state target_cash_pct/cash_pct.
레버리지: 자산별 유효레버 min(펀드,자산max), mmr=1/(2×자산max). 청산은 절대가격.
결제통화: 레지스트리 quote(메인+xyz=USDC, vntl=USDH). 잔고체크는 Keeper 단계.
자산 레지스트리: 전 dex(perpDexs 동적, 병렬호출) 283개, 중복은 거래량 큰 dex로 통합.
  분류는 키워드 우선→dex 폴백(_classify). 카테고리 crypto/tradfi(stock/index/commodity/fx)/preipo.
  Pre-IPO=실제 비상장만(SPACEX/OPENAI/ANTHROPIC/SPCX/QNT), 테마바스켓(MAG7/SEMIS등)=index.
  마켓·팔레트 탭 HL식 세분화(주식/지수/원자재/FX). 펀드개설 팔레트 분류 일괄추가.
  스테이블/크립토성(USDE 등)은 crypto 강제(_CRYPTO_FORCE).
  펀드 운용 자산 최대 10종 캡(투표 부담 방지, OMR 카드 X). 백엔드+프론트 강제.
  ※ 거래량 0(죽은 마켓) 자산 제외는 추후.
NAV: 분 단위 upsert(같은 분 덮어쓰기) SQLite 영속.
※ 구 단일 paper.py·정적 web/ 제거 완료. 프론트는 web-next(:3010)만.

#### web-next 주요 컴포넌트 (2026-06-11)
```
app/page.jsx     백테스트(시나리오토글/내스탠스/로그/자산기여도 + 종목·펀딩·상대가격)
app/paper        페이퍼(투표·NAV·자산별테이블[수익/펀딩/평단/청산거리]·리더보드)
app/market       마켓 타일그리드(카테고리/검색/정렬/즐겨찾기/lazy스파크)
components/
  AssetModal     티커 상세 모달(캔들 OHLC호버·펀딩·상대가격)
  AssetPicker    ⌘K 커맨드팔레트(검색·키보드·즐겨찾기) — 마켓검색+상대가격선택 재사용
  Charts         MultiLine/Candles(휠줌·OHLC콜백)/Line/Spark
```
- 펀딩/캔들: 페이지네이션(730일), HIP-3 prefix(xyz:NVDA), /api/relative는 쿼리파라미터
- 로딩: _post 세마포어(8)+재시도, /api/sparks 배치, IntersectionObserver lazy
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
