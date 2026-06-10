# GovernanceFund — 백테스트 & 페이퍼 트레이딩

투표 → 비중 결정 엔진 + 백테스트/페이퍼 트레이딩 웹사이트.
GovernanceFund 본체의 **검증·온보딩 레이어**(돈 없이 메커니즘 체험).

## 구조

```
governance/
  engine/        ← 투표→비중 핵심 로직 (노트북에서 추출, 검증됨)
    profiles.py    코인/프로파일/변동성
    alpha.py       adaptive_alpha (투표주기 적응형 EMA)
    voting.py      simulate_votes, votes_to_target, apply_ema
    prices.py      HL 캔들/현재가 수집 (캐시)
    scenarios.py   백테스트 투표 시나리오 생성기
    backtest.py    run_backtest, calc_metrics
  api/           ← FastAPI 백엔드
    main.py        엔드포인트 (config/prices/backtest/paper)
    paper.py       페이퍼 트레이딩 상태 (인메모리 MVP)
  web/           ← 정적 프론트 (lightweight-charts)
    index.html, style.css, app.js
  tests/
    test_engine.py 엔진 검증 (assert)
```

## 실행

```bash
# 의존성
pip install -r governance/requirements.txt

# 엔진 검증 (선택)
python governance/tests/test_engine.py

# 서버 실행 (레포 루트에서)
python -m uvicorn governance.api.main:app --port 8099

# 브라우저
http://127.0.0.1:8099
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
