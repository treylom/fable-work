# fable-week 차용 개선 계획 (2026-07-03)

> 입력: [hugh-kim.space/fable-week.html](https://hugh-kim.space/fable-week.html) — "모델이 바뀌어도 하네스는 남는가" (Hugh Kim, 5일 하네스 수술 기록). 지시: 재경님 2026-07-03 13:07 "fable-work에 이 문서 참고해서 개선".
> 우리 fable-work 현황: rules(예시 레이어) + hooks(stop-verify-gate + verify-ledger) + bench(스타일 전이 측정). fable-week의 갭 6개 중 우리에게 없는 것과 있는 것을 가른 뒤 차용.

## 진단 — fable-week 시스템 ↔ fable-work 현황 대비

| fable-week 시스템 | 우리 현황 | 판정 |
|---|---|---|
| 검증 자산 ① replay corpus (과거 위반 fixture 재생, block rate 측정) | hooks/tests 일부 존재하나 "실제 뚫린 위반의 박제" 개념·rate 측정 없음 | **차용 1순위** |
| 검증 자산 ② practice probe (파이프라인 결정론 계약, gold label) | bench가 *스타일 전이*를 측정 — *게이트 계약*을 검사하는 probe는 없음 | **차용 2순위** |
| 검증 자산 ③ requirements-lock (기능 삭제 감지 = 완료 편향 차단) | 없음 | **차용 3순위** |
| rule 신진대사 (삼분류 triage + coverage-map + rule-budget 게이트) | rules는 예시 소량이라 비만 문제 없음 — 단 **budget 게이트는 설치자용 가치** | 부분 차용 |
| weekly-scoreboard (NA fail-loud) | 없음 — 개인 설치자에겐 과설계 가능 | 보류(문서화만) |
| 전환 리허설 (substrate 지표 사전 고정, 두 체제 delta 0) | **bench가 이미 이 사상** (harness ON/OFF × 모델) — "전환 delta" 프레임만 부재 | 프레임 차용 |
| decision-history (기각 대안 영속) | docs에 산재 | 경량 차용 |

## 실행 항목 (우선순위순)

### P1. replay corpus — `hooks/tests/replay/`
- 구조: `replay/fixtures/<violation-name>/` (재현 입력 + expected=BLOCK) + `replay/run.sh` — 전 fixture를 게이트에 재생해 `blocked/total` rate 출력, 100% 미만이면 exit 2.
- 씨앗 fixture: 우리 게이트가 실제로 잡아온 위반 유형을 일반화해 5종 내외 박제(예: 검증 없는 완료 선언, 증거 없는 GREEN, 회의 log 누락). **corpus-floor 검사 동봉**(fixture 수가 기준 이하로 줄면 exit 2 — fable-week D5가 잡은 "fixture 삭제로 100% 위조" 게임 벡터 봉쇄).
- README에 "위반이 실제로 발생할 때마다 fixture로 박제하라"는 운영 규약 명시.

### P2. practice probe — `hooks/tests/probes/`
- 게이트 파이프라인의 결정론 계약 probe: ①verify-ledger가 증거 없는 DONE에 exit 2 ②stop-verify-gate가 코드 변경+무검증 종료에 발화 ③ledger 스키마 필드 계약. gold label은 저장소에 고정(fixture 입력 + 기대 exit code).
- `run.sh`에서 replay와 함께 실행 — probe N/N 출력.

### P3. requirements-lock — `hooks/requirements-lock.py` (옵션 게이트)
- 사용자가 `requirements.lock`(잠긴 요구의 코드 시그니처 목록 — 함수명/파일/grep 패턴)을 선언하면, 커밋 전 시그니처 소실 시 exit 2. "에러를 없애려고 기능을 없애는" 완료 편향 차단.
- 옵션(파일 없으면 no-op) — 설치 마찰 최소화.

### P4. bench에 "전환 리허설" 프레임 추가 — `bench/README.md` + `bench/substrate-check.sh`
- 개념: 모델 전환 전후 **substrate 지표**(replay rate·probe N/N·게이트 등록 수)를 동일 스크립트로 재측정 — delta 0 = "하네스가 모델 비종속"의 측정 증명. 우리 bench의 key finding(harness-dependent 과제에서 하네스가 점수 회복)과 상보: bench=스타일 전이, substrate-check=게이트 불변.
- `substrate-check.sh` = replay rate + probe 수 + hooks 등록 상태를 한 줄 JSON으로 출력(before/after diff용).

### P5. rule-budget 게이트(경량) + decision-history
- `hooks/rule-budget.py`: rules/ 총 바이트·파일 수가 선언 상한 초과 시 경고(exit 2는 옵션) — add+delete 상쇄 우회 대비 순증 기준.
- `docs/decision-history.md`: 이 계획의 채택/기각 결정 기록 시작(보류한 weekly-scoreboard 포함, 사유 명시).

## 게이트 (공개 레포 — porting-infra §2)
구현 후: 시크릿/내부경로 스캔 → hooks 테스트 전체 GREEN(신규 replay/probe 포함) → 글재경 4축 문안 검토(신규 README 문안) → 재경님 push 승인 → push.

## 차용하지 않은 것 (사유)
- weekly-scoreboard cron: 개인 설치자 기준 운영 부담 > 효용 — decision-history에 기각 기록, 대신 substrate-check 수동 1줄 실행으로 대체.
- rule 242→91급 신진대사 절차: 우리 rules는 예시 레이어(소량)라 대상 없음 — 개념만 README에 소개.
