# GovernanceFund — 백테스트 & 페이퍼 트레이딩

투표 → 비중 결정 엔진 + 백테스트/페이퍼 트레이딩 웹사이트.
GovernanceFund 본체의 **검증·온보딩 레이어**(돈 없이 메커니즘 체험).

## 구조

```
governance/
  engine/        ← 핵심 로직 (노트북에서 추출, 검증됨)
    profiles.py    코인/프로파일(공격적·보수적·현물1x)/변동성
    alpha.py       adaptive_alpha (투표주기 적응형 EMA)
    voting.py      simulate_votes, votes_to_target, apply_ema
    prices.py      HL 캔들/현재가/펀딩/상대가격/청산가 (동시성제한·캐시·재시도)
    assets.py      HL 전 자산 레지스트리(크립토+TradFi+Pre-IPO), 배치 스파크
    scenarios.py   백테스트 투표 시나리오 (모멘텀/역추세/이평/랜덤/완벽/커스텀)
    backtest.py    run_backtest, calc_metrics (자산별 기여도 포함)
  api/           ← FastAPI 백엔드
    main.py        엔드포인트 (config/prices/funding/relative/assets/sparks/backtest/funds/paper)
    live.py        HL WebSocket 라이브 가격 워커(메모리) + /ws/market 푸시
    store.py       SQLite 영속(funds/votes/nav_history/allowlist) — DB 자동생성
    funds.py       펀드별 운용 엔진(멀티펀드, 유니버스/영속/라이브평가)
    paper.py       (구) 단일 페이퍼 상태 — 3-4에서 funds로 이전 후 제거 예정
  governance.db    SQLite (gitignore. 첫 실행 시 init_db로 자동 생성 + Demo 펀드 시드)
  web/           ← 구버전 정적 프론트 (대체됨, 보존)
  web-next/      ← ★ Next.js14 + Tailwind 프리미엄 프론트 (현행)
    app/           page(백테스트) · paper · market
    components/    Charts, TopNav, AssetModal, AssetPicker(⌘K)
  tests/
    test_engine.py 엔진 검증 (assert)
```

## 실행 (서버 2개)

```bash
# 백엔드 (레포 루트에서)
pip install -r governance/requirements.txt
python -m uvicorn governance.api.main:app --port 8099

# 프론트 (Next.js)
cd governance/web-next && npm install && npm run dev   # → http://localhost:3010
#   Next가 /api/* 를 8099 백엔드로 프록시

# 엔진 검증 (선택)
python governance/tests/test_engine.py
```

## 기능

### 과거 백테스트 탭
- 프로파일/기간/투표주기 선택 → 시나리오별(모멘텀/역추세/랜덤/완벽예측) 수익률
- Buy&Hold 벤치마크 대비 누적 수익률 곡선
- 성과 지표 (Sharpe, 최대낙폭, 승률, 청산)
- HL 종목 캔들 차트

### 라이브 페이퍼 트레이딩 탭
- 코인별 방향 투표 (-2~+2, Kahoot 스타일)
- 예치금 가중 집계 → 목표 비중 → 실시간 HL 가격으로 가상 NAV
- 펀드 수익률 / 포트폴리오(목표 vs 현재) / 리더보드

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /api/config | 코인/프로파일 메타 |
| GET | /api/prices/{coin}?days= | HL 캔들 |
| POST | /api/backtest | 시나리오 백테스트 |
| POST | /api/paper/vote | 페이퍼 투표 |
| GET | /api/paper/state | 펀드 현황+NAV |
| POST | /api/paper/reset | 세션 초기화 |

## 한계 (MVP)

- 페이퍼 상태는 프로세스 메모리 (재시작 시 초기화) → 추후 SQLite
- 인증 없음 → 추후 지갑 서명
- 단일 펀드 프로파일 (최신 투표 기준)

## 다음 단계

→ AI Keeper 프로토타입 (이 엔진으로 실제 HL 주문 실행)
→ 온체인 투표/예치 컨트랙트
상세: `docs/specs/GovernanceFund_Backtest_spec.md`
