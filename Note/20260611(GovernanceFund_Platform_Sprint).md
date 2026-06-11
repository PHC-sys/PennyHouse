# 2026-06-11 — GovernanceFund 플랫폼 스프린트

> 개발 일지. 결정과 이유 중심. (참조 스펙은 docs/specs/, 사용법은 docs/guides/)

## 한 일 (큰 흐름)
FundingCarryBond 보류 → GovernanceFund로 방향 전환한 뒤, 며칠 만에
"백테스트 → 페이퍼 트레이딩 → 마켓 → 라이브 → 멀티펀드"까지 상업용 수준으로 구축.

```
engine 모듈 추출 → FastAPI + 정적 사이트(MVP)
→ Next.js+Tailwind 프리미엄 재구축
→ 1차(자산별손익/평단/청산가/1x) → 2차(전 자산+마켓탭+모달+⌘K+로딩최적화)
→ 2.5차(HL WebSocket 라이브) → 3차(SQLite 멀티펀드, 3-1·3-2 완료)
```

## 핵심 결정과 이유

### 투표→비중: Target 방식 + 적응형 alpha
- 증분(누적) 방식은 방향 전환이 3~4주 걸려 폐기. Perfect 시나리오조차 손실.
- Target 방식(score가 곧 목표 포지션) + EMA. alpha는 투표주기에 반비례
  (`1 - 0.1^(주기/T)`) → 어떤 주기든 달력 기준 반응속도 동일. assert로 검증.

### 프론트: 정적 HTML → Next.js 재구축
- "어디 내놔도 안 쪽팔릴" 상업용 목표. API-first 유지 → 추후 모바일 앱이 같은 /api 재사용.

### 자산: HL 전 perp (HIP-3 포함)
- 메인 dex(크립토 179) + HIP-3 xyz(TradFi 73) + vntl(Pre-IPO 13) = 265.
- 나머지 HIP-3 dex는 중복(GOLD/NVDA 재상장)이라 제외. 펀드는 유니버스 선택.

### 라이브: Fan-out (HL WS 워커 1개 → 메모리 → /ws 푸시)
- 화면마다 HL 찌르던 구조가 rate limit·느림의 원인.
- 워커 1개가 allMids 구독 → 브라우저는 서버 메모리만 봄.
- "라이브+가벼움": 차트는 전체 재로딩 X, 마지막 봉만 update + 봉 롤오버.

### 멀티펀드: SQLite
- funds/votes/nav/allowlist 영속. 라이브 가격은 메모리 유지.
- kind(demo|real), visibility, 유니버스, 허용지갑(저장만, 인증은 5차).
- 멀티유저 식별은 localStorage 닉네임(인증 전까지).

## 큰 깨달음 — 페이퍼(DB) vs 실제(블록체인)
실제 펀드는 계산이 아니라 **지갑 포지션을 읽음**(entryPx/unrealizedPnl/
liquidationPx/펀딩). → 지갑이 진실의 원천 → 서버 다운/재시작과 무관.
페이퍼는 지갑이 없어 서버가 가상 계산 → 그래서 SQLite·런타임 계산이 필요.
둘은 공존(데모는 DB, 실제는 온체인), 같은 엔진 재사용. DB는 GitHub 미포함.

## 트러블슈팅 메모
- React StrictMode + lightweight-charts: series 참조가 파괴된 차트 가리켜 빈 차트
  → 차트/시리즈 함께 생성하고 cleanup에서 ref null.
- ResizeObserver가 언마운트 후 elRef.current(null).clientWidth → DOM 노드 캡처+isConnected.
- 마켓 로딩 불안정: 타일 120개 개별 spark 호출 폭탄 → 세마포어(8)+배치+IntersectionObserver.
- 펀딩 404: 페이지네이션이 역방향이라 1페이지만 → 전진(ascending) + _post 재시도.

## 다음
3-3 펀드 목록·개설 화면 → 3-4 펀드 상세 → 4차 리플레이 → 5차 지갑 인증.
전체: docs/specs/GovernanceFund_Platform_roadmap.md
