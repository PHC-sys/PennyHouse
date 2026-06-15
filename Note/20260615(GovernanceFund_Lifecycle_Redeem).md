# 2026-06-15 — GovernanceFund 운영 보강 (상장폐지 정산 · 회수 · 삭제)

> 개발 일지. 결정과 이유 중심. (참조 스펙은 docs/specs/, 사용법은 docs/guides/)

## 한 일 (큰 흐름)
3차(멀티펀드) 위에 **운영에 필요한 생애주기/자금흐름**을 채웠다.
버그 2건 수정 + 기능 2건 추가 + UI 탭 1건.

```
USOIL 평단·청산가 누락(버그) → 라이브 워커 전 dex 동적 구독
상장폐지 자산 동결(버그)     → settle-to-cash 정산
지분 회수(신규)              → redeem (share 인출 + 투표 삭제)
펀드 삭제(가드 신규)         → 생성자 + 자금 0일 때만
"내 펀드" 탭(신규)
```

## 핵심 결정과 이유

### 라이브 워커 dex 구독을 동적화
- 워커가 `[main, xyz, vntl]` 3개 dex만 구독했는데, 레지스트리(`fetch_universe`)는
  `perpDexs`로 전체(9개)를 긁어 거래량 기준 대표를 뽑음 → 불일치.
- `km:USOIL`처럼 비주요 dex 자산은 펀딩값만 살고 라이브 가격이 안 들어와
  평단·청산가·손익이 비었다. 워커도 `perpDexs`로 동적 구독하도록 통일.

### Pre-IPO/상장폐지 = settle-to-cash (IPO 자동연결은 포기)
- 실측: HL은 `isDelisted` 플래그 하나뿐. 사유도, 후속 종목 링크도 안 준다.
  - `vntl:SPACEX`=진짜 delisted, `vntl:BIOTECH`=vol0이지만 정상 → delisted와 거래량0은 별개.
  - `vntl:GOLDJM/SILVERJM`도 delisted → delisting은 IPO 전용이 아님(계약 교체).
- 따라서 "IPO 전환 감지/자동 stock 연결"은 데이터로 불가. 풀 수 있는 건 **보유 포지션 정산**.
- 보유 자산이 delist되면 마지막 mark로 청산 → 비중0/현금/손익동결/"정산됨".
  실제 HL이 perp delist 시 미결제 포지션을 최종 mark로 강제정산하는 것과 동일.
- 후속종목 매핑(`PREIPO_SUCCESSOR`)은 훅만 비워둠 — HL에 실제 후속주 생기면 한 줄 추가.

### 지분 회수(redeem)는 비중이 아니라 '출금'
- 전부터 정리해 둔 원칙: 개인 "정리"는 가중평균이라 비중을 0으로 못 만든다(거버넌스 본질).
  진짜 빠지는 건 **지분 회수=출금**이며 비중과 분리된 별도 기능.
- share 비율만큼 equity/initial/asset_pnl을 같은 비율로 축소 → **남은 참가자 가치·수익률 불변**.
  투표는 `store.delete_vote`로 영속 삭제. 전원 회수 시 자본 0.
- 페이퍼라 자본 차감은 런타임 메모리(설계 원칙: 실펀드는 지갑 읽기). 투표 삭제만 영속.

### 펀드 삭제에 가드
- 원래 DELETE는 무조건 삭제(+프론트엔 버튼조차 없었음 → 사실상 사용 불가).
- 이제 **생성자 본인 + 자금 0**(예치 합 0 또는 equity≈0)일 때만. 프론트에 삭제 버튼 신규.

## 트러블슈팅 메모
- `apply_ema`가 active uni만 키로 반환 → 정산 자산 키가 빠져 `KeyError` → 집계 후 setdefault로 복원.
- 전원 회수로 자본 0 → 수익률 계산 `ZeroDivisionError` → `_retpct`/`_pnlpct` 가드 추가.

## 검증 (실서버 8129, end-to-end 4/4 통과)
1. USOIL: `km:USOIL` price/평단/청산가 정상 채워짐.
2. settle: `vntl:SPACEX` settled=true, 비중0, 최종가 고정, 현금 흡수.
3. redeem: alice 회수 → equity 100k→75k, bob 가치 75k 보존.
4. delete: 자금남음 400 → 전원회수 → 비생성자 403 → 생성자+자금0 200 → GET 404.

## 런타임 스냅샷 영속화 (같은 날 추가)
- 증상: "코드 수정하면 라이브 테스트하던 펀드가 사라진다."
- 진단: 펀드 자체(메타/투표/NAV)는 SQLite라 멀쩡. 사라진 건 **런타임 평가상태**
  (equity/평단/손익) — 메모리라 백엔드 재시작마다 리셋됐던 것. DB가 지워지는 게 아님
  (governance.db는 governance/.gitignore의 *.db로 무시, git이 안 건드림).
- 해결: fund_runtime 테이블에 런타임 JSON 스냅샷 저장·복원.
  · 저장: _mark_to_market 쓰로틀(8s) + 투표/회수 직후 force.
  · 복원: _rt가 메모리에 없으면 load_runtime → 있으면 그대로 복원(+상장폐지 재반영),
          없으면 기존대로 fresh+aggregate.
  · reset/delete 시 스냅샷도 삭제. redeem으로 줄인 initial/equity도 보존됨.
- 검증: 펀드 생성·투표(BTC평단 65539.5) → 서버 kill/재시작 → 평단 65539.5 그대로 복원.

## 다음
- 미해결: 자산 분류/검색 별칭(2번 — SpaceX→SPCX 등).
- 4차 리플레이 착수 후보. 전체: docs/specs/GovernanceFund_Platform_roadmap.md
