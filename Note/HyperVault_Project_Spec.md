# HyperVault — 프로젝트 설계 문서
> **원클릭 델타뉴트럴 캐리 포지션 플랫폼**
> HyperEVM 기반 / 유저는 USDC 입력 한 번만
> 작성일: 2026-05-25 / 수정일: 2026-05-27


---

## 0. 핵심 컨셉 (한 줄 정의)

> **유저가 USDC를 넣으면, 원클릭으로 델타뉴트럴 캐리 포지션이 자동으로 구성되는 플랫폼**

```
유저가 할 것:    USDC 금액 입력 → 버튼 1번

컨트랙트가 할 것:
  ① 750 → uETH 현물 롱 (HyperCore 스팟)
  ② 250 → ETH Perp 3x 숏 (HyperCore Perp)
     → 현물 롱 750 = Perp 숏 노출 750 → 델타 = 0
  ③ uETH → HyperLend 담보 → USDC 차입 → 루프 반복
     → 실질 1.46x 레버리지 (LTV 65%, 75/25 split 유지 기준)
  ④ 펀딩비 자동 수취
  ⑤ +-20% 도달 시 자동 리밸런싱
  ⑥ 펀딩비 음수 전환 시 자동 모드 전환
```

---

## 1. 프로젝트 개요

### 핵심 아이디어
Hyperliquid의 ETH Perp 펀딩비(역사적 평균 연 10.95%, 8시간당 약 1bp)는 장기적으로 양수 편향을 가진다. 이를 델타뉴트럴 포지션으로 수취하고, HyperLend 루프를 통해 레버리지를 적용해 자본 대비 수익률을 극대화하는 온체인 Vault.

### 수익 구조 요약
```
수익원 1: ETH Perp 숏 포지션 → 펀딩비 수취 (양수 구간)
수익원 2: uETH 현물 롱 → HyperLend 루프로 레버리지 증폭
비용:     USDC 차입 이자 6.53% - uETH supply 이자 1.29% (net 약 -4.32%, 실측 기준)

기대 수익 (연, 자본 대비):
  보수적 (펀딩 7%):    ~5.9%
  중간   (펀딩 10.95%): ~11.7%
  낙관적 (펀딩 15%):   ~17.6%

산출식: 펀딩률 × 1.463 (Perp 노출 배수) - 4.32% (렌딩 순비용)
```

### 기술 스택
- **체인**: HyperEVM (Hyperliquid L1)
- **렌딩**: HyperLend (uETH 담보 → USDC 차입)
- **Perp**: HyperCore (CoreWriter Precompile)
- **스팟**: HyperCore (CoreWriter Precompile)
- **컨트랙트**: Solidity + Foundry
- **프론트**: Next.js + wagmi + viem + Tailwind
- **봇**: Python Keeper
- **배포**: Vercel (웹) + Render (봇)

---

## 2. 포지션 구조

### 기본 구성 (USDC 1,000 기준)

```
Step 1: 초기 포지션
  750 USDC → uETH 현물 롱 (HyperCore 스팟)
  250 USDC → Perp 3x 숏 마진 (750 USDC 노출)
  → 현물 750 = Perp 노출 750, 델타 = 0

Step 2: HyperLend 루프 (LTV 65%)
  750 uETH → HyperLend 담보 예치
  → USDC 487 차입 (65% LTV)
  → 다시 현물 롱 75% + Perp 숏 마진 25% (비율 유지)

Step 3: 반복 (4~5회)
  수렴식: S = 750 / (1 - 0.65 × 0.75) = 750 / 0.5125
  수렴값: 실질 노출 1.46x
```

### 실질 포지션 (수렴 후)
```
총 현물 롱:  1,463 USDC 상당 uETH
총 Perp 숏:  1,463 USDC 상당
총 차입금:     951 USDC 상당

델타:        ≈ 0 (현물 롱 + Perp 숏 상쇄)
수익원:      펀딩비 수취 + 렌딩 net

※ 루프마다 75/25 비율(현물/Perp마진) 유지 시 수렴값.
  델타뉴트럴 조건: 루프 전 과정에서 현물 노출 = Perp 노출 유지 필요.
```

---

## 3. 리스크 파라미터

### 청산 레벨
```
HyperLend 담보 청산:  uETH 가격 약 -30% (HyperLend 청산 임계 LTV 기준, 실측 확인 필요)
Perp 숏 청산:         ETH 가격 +33% (3x 기준)

경고 트리거 (디레버리징 시작): +-20%
청산 레벨:                     Perp +33% / 담보 약 -30%

※ 경고(+-20%) → 청산(+33%) 사이 버퍼: 13%p
  Keeper 봇 응답 지연 + CoreWriter 비동기 감안 시 촘촘한 편.
```

### 펀딩비 전환 대응
```
펀딩비 음수 전환 시:
  모드 전환 → USDC supply + uETH 차입 + 현물 숏 + Perp 롱
  전환 비용: 왕복 약 0.14% (taker 0.035% × 4)
  손익분기: 음수 6일 이상 지속 시 전환 유리

전환 트리거 조건 (누적 손실 기반):
  accumulatedFundingLoss > SWITCH_COST_THRESHOLD
```

### 손익분기 펀딩비
```
렌딩 순비용 4.32% (실측: USDC 차입 6.53% × 951 - uETH 공급 1.29% × 1,463) / 1,000:
  순비용 4.32% / Perp 노출 배수 1.463 = 연 2.95%
  → 펀딩비 연 2.95% 이상이면 수익
  → 역사적으로 거의 항상 충족
```

---

## 4. 컨트랙트 아키텍처

### 주요 컨트랙트

```
HyperVault.sol          // 메인 Vault (ERC-4626)
├── deposit()           // USDC 예치, 포지션 진입 시작
├── withdraw()          // 포지션 청산 후 USDC 반환
├── loop()              // HyperLend 루프 실행 (Keeper 호출)
├── deleverage()        // 디레버리징 (경고 레벨 도달 시)
├── switchMode()        // 펀딩비 음수 시 포지션 방향 전환
└── harvest()           // 펀딩비 수익 누적

CoreWriterInterface.sol // HyperCore 호출 인터페이스
├── openSpotLong()      // uETH 현물 매수
├── openPerpShort()     // ETH Perp 숏
├── closeSpotLong()     // 현물 청산
└── closePerpShort()    // Perp 청산

HyperLendInterface.sol  // HyperLend 호출 인터페이스
├── supplyCollateral()  // uETH 담보 예치
├── borrowUSDC()        // USDC 차입
├── repay()             // 차입 상환
└── withdraw()          // 담보 회수
```

### 상태 변수 (핵심)
```solidity
uint256 public totalDeposited;      // 총 예치 USDC
uint256 public totalSpotExposure;   // 총 현물 노출
uint256 public totalPerpExposure;   // 총 Perp 노출
uint256 public totalBorrowed;       // HyperLend 총 차입
uint256 public loopCount;           // 현재 루프 횟수
bool    public isLongMode;          // true=롱모드, false=숏모드
int256  public accumulatedFunding;  // 누적 펀딩비
```

### CoreWriter 비동기 처리 (2-Phase Commit)
```
Phase 1: CoreWriter 호출 → 큐 등록
Phase 2: 다음 블록에서 Precompile로 체결 확인
         → 실패 시 pending 상태 유지, 재시도
         → 성공 시 다음 단계 진행
```

---

## 5. Keeper 봇 설계

### 역할
```
1. 펀딩비 모니터링 (8시간마다)
2. 루프 단계별 순차 실행 (CoreWriter 비동기 대응)
3. Health Factor 감시 (1분마다)
4. 디레버리징 트리거
5. 모드 전환 (펀딩비 음/양수 전환 감지)
```

### 로직 흐름
```python
while True:
    funding_rate = get_hyperliquid_funding_rate("ETH")
    health_factor = get_hyperlend_health_factor(vault_address)

    # 청산 위험
    if health_factor < 1.2:
        trigger_deleverage()

    # 펀딩비 모드 전환
    if accumulated_loss > SWITCH_THRESHOLD:
        trigger_switch_mode()

    # 정상 루프 실행
    if pending_loop_step:
        execute_next_loop_step()

    sleep(60)
```

---

## 6. 프론트엔드 설계

### 웹사이트 (Next.js)
```
페이지 구성:
  /           → 랜딩 페이지 (수익률, 구조 설명)
  /app        → 메인 대시보드
  /app/deposit → 예치 화면
  /app/withdraw → 출금 화면

대시보드 주요 지표:
  - 현재 포지션 현황 (현물/Perp 노출)
  - 누적 수익률
  - 현재 펀딩비 (8시간/연환산)
  - Health Factor
  - 청산 레벨까지 남은 거리
  - 모드 (롱/숏)
  - 펀딩비 히스토리 차트
```

### 모바일 (PWA)
```
웹사이트를 PWA로 래핑
추가 네이티브 기능:
  - 청산 위험 푸시 알림
  - 펀딩비 전환 알림
```

---

## 7. 비용 추정

### 초기 개발 단계 (MVP)
```
도메인 (.xyz):          $5/년
Vercel (웹):            무료
Render (봇):            무료~$7/월
HyperEVM 배포 가스비:   $10~50 (HYPE)
Hyperliquid 퍼블릭 RPC: 무료

총 초기비용:            ~$50
```

### 실서비스 단계
```
스마트컨트랙트 감사:    $5,000~20,000 (필수)
QuickNode RPC:          $49/월 (트래픽 증가 시)
법률 검토:              별도 (선택)
```

---

## 8. 개발 로드맵

```
Phase 1 (2~4주): 스마트컨트랙트
  □ HyperVault.sol 작성
  □ CoreWriterInterface.sol
  □ HyperLendInterface.sol
  □ Foundry 테스트 작성
  □ HyperEVM 테스트넷 배포
  □ 2-Phase Commit 검증

Phase 2 (2~3주): Keeper 봇
  □ 펀딩비 모니터링
  □ 루프 순차 실행 로직
  □ Health Factor 감시
  □ 디레버리징/모드 전환
  □ Render 배포

Phase 3 (3~4주): 웹 프론트
  □ Next.js 프로젝트 세팅
  □ wagmi + viem 연동
  □ 대시보드 UI
  □ 예치/출금 플로우
  □ Vercel 배포

Phase 4 (2~3주): 모바일/고도화
  □ PWA 설정
  □ 푸시 알림
  □ 펀딩비 히스토리 차트
  □ 백테스트 결과 시각화

Phase 5 (별도): 실서비스
  □ 스마트컨트랙트 감사
  □ 메인넷 배포
  □ 유저 테스트
```

---

## 9. ⚠️ 향후 결정 필요 사항

아래 항목들은 개발 전 또는 개발 중 반드시 결정해야 함.

### 컨트랙트 파라미터
```
[ ] 루프 최대 횟수 고정값 (추천: 4~5회)
[ ] LTV 기준값 (현재 가정: 65%)
[ ] 디레버리징 트리거 임계값 (현재 가정: +-20%)
[ ] 청산 레벨 (Perp 기준: +33%, HyperLend: 실측 확인 필요)
[ ] Perp 배율 (현재 가정: 3x)
[ ] 펀딩비 전환 트리거 누적 손실 임계값
[ ] 최소/최대 예치 금액
[ ] Vault 운용 수수료율 (performance fee %)
```

### 프로토콜 확인 필요
```
[x] HyperLend uETH 담보 → USDC 차입 Pool 존재 여부
    → 확인 완료. uETH Supply APY 1.29%, USDC Borrow APY 6.53%
[ ] uETH를 HyperCore 스팟에서 바로 매도 가능한지
    → CoreDepositWallet 브릿징 경로 확인
[x] HyperLend USDC 실제 차입 이자율
    → 실측 6.53% (2026-05-27 기준)
[x] USDC supply 이자율 확인
    → 실측 4.41% (2026-05-27 기준)
[x] uETH supply 이자율 확인
    → 실측 1.29% (2026-05-27 기준)
[ ] CoreWriter 오더 타입 (limit vs market) 결정
[ ] HyperLend 정확한 청산 임계 LTV 확인 (담보 청산 가격 계산용)
```

### 서비스 설계
```
[ ] 프로젝트/사이트 이름 결정
[ ] .xyz 도메인 구체적 이름 결정
[ ] Vault 접근 제한 여부 (누구나 vs 화이트리스트)
[ ] 운용 수수료 구조 결정
[ ] 토큰 발행 여부 (거버넌스 토큰 등)
[ ] 멀티시그 운영자 구성
```

### 법적/컴플라이언스
```
[ ] 서비스 대상 지역 제한 여부
[ ] 한국 거주자 접근 허용 여부
[ ] 면책 조항 문구
[ ] 감사 업체 선정 (실서비스 전)
```

---

## 10. Claude Code 시작 프롬프트

Claude Code 세션 시작 시 아래를 첫 메시지로 사용:

```
HyperEVM 기반 델타뉴트럴 펀딩비 캐리 Vault를 만들려고 해.

스펙:
- HyperEVM (Solidity + Foundry)
- HyperLend (uETH 담보 → USDC 차입, Borrow APY 6.53%)
- HyperCore CoreWriter로 스팟 매수 + Perp 숏 실행
- ERC-4626 Vault 구조
- LTV 65%, 루프 4~5회, Perp 3x (750 노출 / 250 마진, 델타뉴트럴)
- 루프마다 차입금 75% → 현물, 25% → Perp 마진 비율 유지
- 수렴 레버리지: 1.46x (총 현물/Perp 노출 1,463 USDC / 1,000 기준)
- 리밸런싱 트리거: +-20% (Perp 청산 +33% 전에 먼저 발동)
- CoreWriter 비동기 처리를 위한 2-Phase Commit 패턴 적용

먼저 Foundry 프로젝트 세팅하고
HyperVault.sol 뼈대부터 작성해줘.
CoreWriter 인터페이스는
0x3333333333333333333333333333333333333333 주소 기준으로.
```

---

*문서 끝 — 이 문서를 기반으로 Claude Code에서 개발 시작*
