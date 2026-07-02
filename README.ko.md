# fable-work

**"강한 모델이 일하는 방식"을 하네스로 옮기는 방법 — 규칙 + 검증 게이트 + 벤치마크 — 그래서 다른 모델도 그 일하는 방식을 물려받게 한다.**

> 🌐 English: **[README.md](README.md)**

`fable-5`는 실제 모델이다 — Anthropic의 Fable 5(`claude-fable-5`), Claude 5 패밀리. 단 며칠간의 실사용만으로도 이 모델과 손발 맞춘 방식이 제법 좋은 *작업 방식*으로 자리 잡았다: 목표를 정직하게 쪼개고, "완료"라 말하기 전에 검증하고, 막힌 데를 돌려 말하지 않고 그대로 보고했다. 그 방식의 상당 부분은 모델의 가중치(weight)에 있지 않다 — 모델 주변에 쌓인 습관과 스캐폴딩(scaffolding, 모델을 둘러싼 뼈대 구조물)에 산다. `fable-work`는 그 스캐폴딩을 **외부에 인코딩**하려는 시도다 — 이식 가능한 하네스(상황별 규칙 파일 + 기계적 검증 게이트)로 만들고, 하네스를 켰을 때 그 일하는 방식이 다른 — 대개 더 저렴한 — 모델(예: `sonnet` 급)에 **얼마나 실제로 이전되는지 측정**한다.

이 레포는 그 하네스의 공개·일반화 배포판이다. 개발 환경의 내부 이름·경로·식별자는 제거했고, 로직과 측정 방법론은 그대로다.

![인포그래픽](./docs/infographic-ko.png)

## 핵심 발견

같은 과제셋을 비슷한 급의 두 모델(`fable-5`·`sonnet-5`)에 **둘 다 하네스 없이** 돌렸다 — 맨몸(vanilla) 대조군(scratch 작업 폴더, 하우스 룰 미로드). 과제는 두 종류로 깔끔히 갈렸다:

| 과제 분류 | 예시 | 맨몸(vanilla) 평균 점수 |
|---|---|---|
| **하네스 의존** — 정답이 특정 성문(成文) 규칙에 살아 있고, 일반 역량으로는 안 됨 | 빌드 전 아웃라인 먼저, 이미지 편집 vs 생성, 리서치 위임 | **~62** |
| **일반 추론** — 유능한 모델이면 규칙 없이도 맞힘 | 팩트체크, 카드뉴스, 지식 저장, 글쓰기 | **~90** |

**이 ~28점 격차가, 하네스를 켰을 때 회복될 것으로 기대되는 몫이다.** 이것은 "모델이 원하는 대로 안 했다"를 두 갈래로 분리한다 — 실제로는 *규칙 커버리지* 문제(모델이 그 규칙을 본 적이 없음)이지 *역량* 문제(추론을 못 함)가 아닌 부분. 하네스 의존 과제는 규칙·게이트 시스템이 고치라고 있는 바로 그 과제이고, 일반 추론 과제는 같은 모델이 그 외엔 멀쩡함을 보여주는 대조군이다.

같은 측정에서 나온 두 가지 더 — 어떤 "하네스가 도왔다" 수치든 이걸 알고 읽어야 한다:

- **성문 규칙은 강제(enforcement)가 아니다.** 이식한 검증 게이트(`Stop` 훅 패턴, [docs/method.md](docs/method.md) 참조)가 작업 도중 **그 게이트를 만든 사람 자신의 세션을 실제로 차단**했다. 이건 버그 리포트가 아니라, 게이트가 장식 문서가 아니라 기계적으로 살아 있었다는 증거다. 규칙이 한 번도 발동 안 하면, 그게 배선됐는지 사실 알 수 없다.
- **점수 격차의 일부는 모델 문제가 아니라 측정 장비 문제다.** 모델의 자기보고로 채점하는 대신 도구 사용 기록(실제로 어떤 명령이 돌았는지의 증거)을 보존했더니, 고난도 보안 벤치가 93 → 96으로 올랐다 — 앞의 낮은 점수는 대체로 채점자가 모델이 실제로 한 작업을 못 본 것이지, 모델이 안 한 게 아니었다.

### 스코어보드 (Cycle 1 — 맨몸/하네스 off)

| 벤치마크 | fable-5 | sonnet-5 |
|---|---:|---:|
| core-3 (코드수정·보안·오케스트레이션) | 89.9 | 86.7 |
| hard-security | 96.5 | 95.2 |
| real-work-7 (실작업 7종) | 79.3 | 75.3 |

### `fable`과 비교 모델은 어디서·왜 다른가

두 열 다 맨몸(vanilla) 상태다 — 하네스 미로드. 그러니 `fable-5` vs `sonnet-5` 격차는 하네스 없는 **두 모델의 raw 차이**다 — 관심사는 *어디서* 갈리고 *근거가 무엇인가*다. 격차는 균일하지 않다:

- **판단이 필요한 과제에 집중된다.** 오케스트레이션: **96.3(무결함)** vs **88.3(P1)** — `fable-5`는 컨텍스트 부족 워커에 *하드 게이트*(막고→해소→재배정)를 걸었고, 비교 모델은 "정리 어려우면 진행"을 허용(규율 스킵). 제약 있는 글쓰기: **93.3** vs **76.7(P1)** — `fable-5`는 "외부 참조 금지"를 지켰고 상대는 어겼다.
- **기계적 과제에선 거의 사라지거나 역전된다.** 단순 시크릿 스캔·코드수정에선 비교 모델이 `fable-5`와 *동급이거나 앞선다* — **~2.5~3배 저렴**하게.

정직한 결론: **`fable-5`의 강점은 모호함 속 판단 — 위험한 단계에 게이트 걸기·제약 지키기·더 철저히 감사하기 — 이지 전반적 우위가 아니다.** 기계적 작업은 더 싼 모델로 라우팅하는 게 맞다. 과제별 근거는 [`bench/results.md`](bench/results.md)에.

**채점 방식**(여섯 축 — A1–A5 + 과제별 SPECIAL — P0/P1 결함 게이트, 실제 도구사용 transcript로 판정)과 **과제별 결과** 전문은 [`bench/results.md`](bench/results.md)에 있다. 축·기준점은 [`bench/rubric.md`](bench/rubric.md), 채점 절차는 [`bench/judge-prompt.md`](bench/judge-prompt.md)를 보라.

## 레포 구조

```
fable-work/
├── README.md / README.ko.md  — 소개 (영어 / 한국어)
├── LICENSE                     — MIT (이 레포 자체 기여분)
├── NOTICE                      — 이식한 훅 설계의 Apache-2.0 출처 표기
├── docs/
│   ├── method.md                — 이전 방법: 규칙 패턴, 검증 원장/스톱게이트, 벤치 루프
│   └── infographic-en.png / infographic-ko.png  — 요약 그래픽 (en / ko)
├── hooks/                       — 일반화된 검증 훅 (규칙 패턴 + 증거 원장 + 스톱게이트)
├── bench/                       — 하네스 의존 vs 일반 추론 과제셋·채점·결과
└── codex/README.md              — Codex에서 쓰는 법 (upstream fable-ish-codex 플러그인 경유)
```

## 빠른 시작

**1. 훅을 당신의 하네스에 설치.** `hooks/`는 검증 라이프사이클의 일반화된 형태 — 세 파일이다:

- **`fable_lib.py`** — 공유 라이브러리. "하네스/코드 표면" 휴리스틱이 어느 변경 파일에 검증 증거가 필요한지 판정하고(일반 노트·마크다운은 면제), 추가전용 증거 원장이 검증을 기록하며(프로젝트 트리 밖에 둬서 커밋 안 됨), 파일럿 게이트 킬스위치(`FABLE_GATE_OFF=1`, 또는 `FABLE_GATE_PILOT=<name>`으로 한 세션에만 먼저 적용). 나머지 두 훅이 이걸 import.
- **`verify-ledger.py`** — `PostToolUse(Write|Edit|Bash)` 훅. 도구 호출 후 그 동작이 실제 검증(테스트 실행·스캔·교차확인)이면 순서 있는 원장에 증거로 기록. 기록만 하고 차단은 안 함. fail-open.
- **`stop-verify-gate.py`** — `Stop` 훅. 하네스/코드 표면을 바꾼 *뒤* 그 변경 이후 성공한 검증 기록이 없는데 턴을 끝내려 하면 `{"decision":"block"}`을 내보내 Stop을 한 번 되돌리고 실제로 검증하라고 알린다. `MAX_STOP_BLOCKS` 상한·루프가드 통과·fail-open — 깨진 훅이 세션을 막는 일은 없다.

`verify-ledger.py`는 하네스의 post-tool-use 이벤트에, `stop-verify-gate.py`는 stop/turn-end 이벤트에 배선(둘 다 `fable_lib.py` import). 배선 후 `hooks/tests/test_gate.py` 실행 — 게이트 계약의 실행 가능한 명세다. Codex라면 아래 [Codex 통합](#codex-통합)의 upstream 플러그인을 권장.

**2. 벤치마크 실행.**

```bash
# 한 fixture를 한 모델로 실행, 전체 도구사용 transcript 보존
bench/run.sh example-codefix <your-model-id> my-run
# 산출물 → $FABLE_BENCH_RUNS_DIR (기본 ~/.fable-bench/runs/): work/ transcript.jsonl raw-output.json meta.json
```

그다음 심판(가능하면 **다른 모델 패밀리**)에게 `bench/rubric.md` + fixture 답안키 + 실행 transcript를 `bench/judge-prompt.md` 템플릿으로 채점시킨다. 러너 옵션·채점 조립 방식·fixture 작성/런타임 트랩 패턴은 [`bench/README.md`](bench/README.md)·[`bench/results.md`](bench/results.md)에 있다.

`bench/`에서 같은 과제셋을 하네스 off(맨몸)/on으로 돌려 위의 이분(二分)을 보고한다. *당신의* 하네스 설치가 *당신의* 베이스 모델에서 실제로 격차를 회복하는지 확인하는 용도 — 위 수치는 하나의 측정이지 보편 상수가 아니다.

## Codex 통합

Codex라면, 이 프로젝트의 훅 설계가 차용한 upstream 플러그인 — `fable-ish-codex` (Apache-2.0, Pandoll-AI) — 을 직접 설치하는 편이 낫다. [`codex/README.md`](codex/README.md) 참조.

## 라이선스

이 레포 자체 기여분은 [MIT](LICENSE). `hooks/` 아래 훅 설계는 `fable-ish-codex`(Apache-2.0, Copyright Pandoll-AI)에서 차용 — 출처 표기는 [NOTICE](NOTICE) 참조.
