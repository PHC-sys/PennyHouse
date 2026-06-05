# HyperVault — 프로젝트 계획서
> 작성일: 2026-05-27
> 목적: 델타뉴트럴 펀딩 캐리 Vault 개발 계획 및 로드맵

---

## Executive Summary

| 항목 | 내용 |
|---|---|
| **플랫폼** | Hyperliquid (HyperEVM) |
| **전략** | ETH 델타뉴트럴 펀딩비 캐리 + HyperLend 레버리지 루프 |
| **기대 수익** | 연 11.7% (펀딩비 10.95% 기준, 자본 대비) |
| **손익분기** | 펀딩비 연 2.95% 이상 (역사적으로 거의 항상 충족) |
| **실질 레버리지** | 1.46x (LTV 65%, 75/25 split 유지 기준) |
| **개발 기간** | MVP 8~12주 |
| **초기 자본** | 자체 자금 $5~10k (외부 TVL 없이 시작) |
| **최종 목표** | 온체인 구조화 상품 플랫폼 |

---

## 1. 전략 개요

### 무엇을 만드는가

유저가 USDC를 넣으면, 자동으로 델타뉴트럴 포지션이 구성되는 온체인 Vault.

```
유저: USDC 입력 → 버튼 1번

자동 실행:
  ① uETH 현물 매수 (HyperCore 스팟)
  ② ETH Perp 3x 숏 (HyperCore Perp) → 델타 = 0
  ③ uETH 담보 → USDC 차입 → 반복 (HyperLend 루프)
  ④ 펀딩비 자동 수취
  ⑤ 가격 ±20% 도달 시 자동 리밸런싱
  ⑥ 펀딩비 음수 전환 시 자동 모드 반전
```

### 왜 지금인가

**Hyperliquid 선점 기회:**
- 동일한 전략(Ethena)이 이미 $5B TVL을 증명함
- Ethena는 CEX 기반(반탈중앙화) — HyperVault는 완전 온체인
- HyperEVM 생태계에 이 구조를 구현한 경쟁자 없음
- Hyperliquid ETH 펀딩비가 타 DEX 대비 구조적으로 높음

### 수익 구조 (실측 기준)

```
수익:  ETH Perp 펀딩비 × 1.463 (레버리지 배수)
비용:  USDC 차입 6.53% × 0.951 - uETH 공급 1.29% × 1.463
      = 렌딩 순비용 4.32%

시나리오별 기대 수익 (연, 자본 대비):
  보수적 (펀딩 7%):    5.9%
  중간   (펀딩 10.95%): 11.7%  ← 역사적 평균
  낙관적 (펀딩 15%):   17.6%

손익분기 펀딩비: 연 2.95%
```

---

## 2. 경쟁 환경 및 차별점

### 유사 서비스 비교

| | Ethena (USDe) | HyperVault |
|---|---|---|
| **TVL** | $5B+ | 0 (신규) |
| **전략** | 델타뉴트럴 캐리 | 동일 |
| **실행 방식** | CEX(바이낸스 등) + 중앙화 수탁 | 완전 온체인 |
| **신뢰 주체** | Ethena팀 + 거래소 + 수탁사 | 스마트컨트랙트만 |
| **플랫폼** | 멀티체인 | Hyperliquid 특화 |
| **경쟁 강도** | 레드오션 | 사실상 없음 |

### 핵심 차별점

1. **완전 온체인**: 수탁사·거래소 리스크 없음, 코드만 신뢰
2. **Hyperliquid 특화**: 높은 펀딩비 + HyperLend 루프 통합
3. **선점**: HyperEVM DeFi 생태계 초기 진입

---

## 3. 단계별 제품 로드맵

### V1 — 코어 Vault (현재 목표)
```
기간:   8~12주
대상:   자체 자금 (외부 투자자 없음)
자산:   ETH 단일
레버:   1.46x (HyperLend LTV 65%)
목적:   전략 검증 + 코드 안전성 확인
```

### V2 — 멀티 자산 + HYPE 캐리
```
기간:   V1 완료 후 4~6주
추가:   HYPE 캐리 (Portfolio Margin 현재 지원)
        → HYPE spot + HYPE Perp 숏 → 레버 2.86x 가능
        BTC, SOL 자산 추가
        자동화 고도화
```

### V3 — Portfolio Margin 업그레이드
```
시점:   Hyperliquid이 Portfolio Margin에 uETH 추가 시
효과:   ETH 캐리도 2.86x로 레버리지 상승
        기대 수익: 보수적 14.4% → 낙관적 37.3%
        코드 구조 변경 없이 파라미터 업데이트만으로 적용
```

### V4 — 고정금리 이표채 토큰
```
기간:   V2 완료 + 트랙레코드 6개월 이후
내용:   Vault 수익을 기반으로 고정금리 채권 토큰 발행
        NFT = 청구권 (EMILIO-BOND 개념의 프로덕션 버전)
        이표채 쿠폰 온체인 계산기
        원금/이자 분리 트랜칭
```

### V5 — RWA 통합 (장기)
```
시점:   법적 구조 갖춰진 후
내용:   토큰화 국채(thBILL 등)를 Vault 담보/수익원으로 추가
        기관 자금 유입 채널
        온체인 일드커브 기초 구축
```

---

## 4. 개발 프로세스

> **구분 기준**
> - `[Claude Code]`: Claude Code와 함께 코딩 진행
> - `[자체 학습]`: 직접 이해하고 있어야 하는 영역

---

### STEP 0 — 사전 학습 (1주)

| 항목 | 방법 | 예상 시간 | 구분 |
|---|---|---|---|
| ERC-4626 Vault 표준 | OpenZeppelin 문서 + 예제 1개 | 2시간 | `자체 학습` |
| Foundry 기초 | 공식 문서 + forge test 실습 | 반나절 | `자체 학습` |
| 스마트컨트랙트 보안 패턴 | Consensys 체크리스트 정독 | 1일 | `자체 학습` |
| HyperEVM CoreWriter 문서 | Hyperliquid 공식 문서 | 반나절 | `자체 학습` |
| HyperLend API | app.hyperlend.finance 문서 | 반나절 | `자체 학습` |

**보안 패턴 우선 학습 항목 (남의 돈 전 필수):**
```
① Reentrancy 공격 패턴 및 방어 (CEI 패턴, ReentrancyGuard)
② Access Control 실수 (onlyKeeper, onlyOwner 누락)
③ Oracle 단일 소스 의존 위험
④ CoreWriter 비동기 중간 상태 취약점
```

---

### STEP 1 — 스마트컨트랙트 (3~4주)

#### Phase 1-A: Foundry 세팅 + 뼈대
| 작업 | 구분 |
|---|---|
| Foundry 프로젝트 초기화 | `Claude Code` |
| 디렉토리 구조 설계 | `Claude Code` |
| HyperVault.sol ERC-4626 뼈대 | `Claude Code` |
| 상태 변수 및 이벤트 정의 | `Claude Code` |
| 기본 접근 제어 구조 | `Claude Code` |

#### Phase 1-B: CoreWriter 인터페이스
| 작업 | 구분 |
|---|---|
| CoreWriterInterface.sol 작성 | `Claude Code` |
| 2-Phase Commit 패턴 구현 | `Claude Code` |
| 비동기 상태 관리 로직 | `Claude Code` |
| Phase 간 실패 복구 로직 | `Claude Code` |
| CoreWriter 테스트넷 연동 검증 | `자체 학습 + Claude Code` |

#### Phase 1-C: HyperLend 인터페이스
| 작업 | 구분 |
|---|---|
| HyperLendInterface.sol 작성 | `Claude Code` |
| 담보 예치 / USDC 차입 함수 | `Claude Code` |
| Health Factor 조회 연동 | `Claude Code` |
| 루프 로직 (4~5회 반복) | `Claude Code` |
| LTV 75/25 비율 유지 검증 | `자체 학습` |

#### Phase 1-D: 핵심 로직 + 테스트
| 작업 | 구분 |
|---|---|
| deposit() / withdraw() 구현 | `Claude Code` |
| loop() 루프 실행 함수 | `Claude Code` |
| deleverage() 디레버리징 | `Claude Code` |
| switchMode() 모드 전환 | `Claude Code` |
| Foundry 단위 테스트 전체 | `Claude Code` |
| HyperEVM 포크 테스트 | `Claude Code` |
| 테스트 결과 직접 검증 | `자체 학습` |

---

### STEP 2 — Keeper 봇 (2~3주)

| 작업 | 구분 |
|---|---|
| Python 프로젝트 구조 세팅 | `Claude Code` |
| Hyperliquid 펀딩비 API 연동 | `Claude Code` |
| HyperLend Health Factor 감시 | `Claude Code` |
| 디레버리징 트리거 로직 | `Claude Code` |
| 모드 전환 감지 + 실행 | `Claude Code` |
| CoreWriter 비동기 대응 순차 실행 | `Claude Code` |
| Render 배포 설정 | `Claude Code` |
| 봇 장애 시 알림 설정 | `Claude Code` |
| 봇 동작 모니터링 직접 운영 | `자체 학습` |

---

### STEP 3 — 프론트엔드 (3~4주)

| 작업 | 구분 |
|---|---|
| Next.js 프로젝트 세팅 | `Claude Code` |
| wagmi + viem 지갑 연동 | `Claude Code` |
| 예치 / 출금 플로우 UI | `Claude Code` |
| 대시보드 핵심 지표 표시 | `Claude Code` |
| 펀딩비 히스토리 차트 | `Claude Code` |
| Health Factor + 청산 거리 | `Claude Code` |
| 한국어 UI 완성 | `Claude Code` |
| PWA 설정 + 푸시 알림 | `Claude Code` |
| Vercel 배포 | `Claude Code` |
| UX 흐름 직접 검토 | `자체 학습` |

---

### STEP 4 — 자체 자금 운용 (6개월)

```
목적:  전략 작동 검증 + 코드 안전성 실증
금액:  $5~10k (본인 자금만)
기간:  6개월 연속 운용
기록:  주차별 수익률, Health Factor 로그, 리밸런싱 발생 횟수
```

| 작업 | 구분 |
|---|---|
| 테스트넷 전체 플로우 검증 | `자체 학습` |
| 메인넷 소액 첫 배포 | `자체 학습` |
| 포지션 모니터링 | `자체 학습` |
| 리밸런싱 실제 발동 확인 | `자체 학습` |
| 비정상 케이스 대응 | `자체 학습` |

---

### STEP 5 — 외부 TVL 오픈 (트랙레코드 확인 후)

| 조건 | 기준 |
|---|---|
| 최소 운용 기간 | 6개월 이상 |
| 최대 드로우다운 | -5% 이내 |
| 청산 이벤트 | 0건 |
| 보안 검토 | Code4rena 경연 또는 소규모 감사 |

| 작업 | 구분 |
|---|---|
| Code4rena / Sherlock 경연 등록 | `자체 학습` |
| 취약점 수정 대응 | `Claude Code + 자체 학습` |
| TVL 캡 설정 후 소규모 오픈 | `자체 학습` |

---

## 5. 리스크 및 대응

| 리스크 | 수준 | 대응 |
|---|---|---|
| CoreWriter 비동기 중 헤지 풀림 | 높음 | 2-Phase Commit + 비상 청산 경로 하드코딩 |
| USDC 차입금리 상승 | 중간 | 손익분기 펀딩비 모니터링, 자동 언와인드 |
| 펀딩비 음수 전환 | 중간 | 자동 모드 전환 (6일 이상 음수 시) |
| Keeper 봇 다운 | 높음 | Render 이중화, 헬스체크 알림 |
| 스마트컨트랙트 버그 | 높음 | 자체 자금으로 먼저 운용, 감사 후 오픈 |
| HyperLend 유동성 부족 | 낮음 | 현재 $3M 가용, 소규모 Vault에 충분 |

---

## 6. 재무 계획

### 초기 비용
```
도메인 (.xyz):       $5/년
Vercel (웹):         무료
Render (봇):         $7/월
HyperEVM 가스비:     $10~50
자체 운용 자금:      $5,000~10,000

총 초기 비용:        $5,100~10,100
```

### 수익 시뮬레이션 ($10,000 자본 기준)
```
보수적 (펀딩 7%):    연 $590
중간 (펀딩 10.95%):  연 $1,170
낙관적 (펀딩 15%):   연 $1,760

Portfolio Margin (uETH) 지원 시 (2.86x):
중간 (펀딩 10.95%):  연 $2,570
```

### 감사 비용 (외부 TVL 오픈 시)
```
TVL $0~50k:    Code4rena 경연 (상금 $5~20k 설정)
TVL $50k~500k: 소규모 감사 업체 $5~15k
TVL $500k+:    탑티어 감사 $20k~50k
```

---

## 7. 장기 비전

```
V1 (현재): ETH 델타뉴트럴 캐리 Vault
           → 전략 검증 + 사용자 신뢰 구축

V2~V3:    멀티 자산 (HYPE, BTC, SOL) + 레버리지 업그레이드
           → 플랫폼 TVL 성장

V4:       Vault 수익 기반 고정금리 이표채 토큰
           → 수익을 구조화 상품으로 패키징

V5:       RWA(토큰화 국채) Vault 담보 추가
           → TradFi 자본 온체인 유입 채널
           → 온체인 수익률 곡선 구축 기반
```

---

## 8. 즉시 결정 필요 사항

```
[ ] 프로젝트 이름 및 도메인 확정
[ ] 초기 자본 금액 확정 ($5k vs $10k)
[ ] STEP 0 학습 일정 확정 (1주 블로킹)
[ ] 운용 수수료 구조 결정 (performance fee %)
[ ] 멀티시그 구성 (운영자 지갑 관리 방식)
[ ] HyperLend 정확한 청산 임계 LTV 확인
[ ] CoreWriter 오더 타입 결정 (limit vs market)
```

---

## 참고: 기술 스펙 문서

상세 컨트랙트 아키텍처, 포지션 수렴 계산, 리스크 파라미터 수치는
별도 문서 참조: `HyperVault_Project_Spec.md`

---

*본 계획서는 2026-05-27 기준 HyperLend 실측 금리(USDC 차입 6.53%, uETH 공급 1.29%)를 반영함.*
*Hyperliquid Portfolio Margin uETH 지원 시 레버리지 및 수익률 자동 상향 조정 가능.*
