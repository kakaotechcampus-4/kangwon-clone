# Week 4 실제 Agent 500케이스 테스트 보고서

`student_parts/week04_retrieve_nanas_memory.py`의 메인과제 3개 tool(`add_personal_reference`,
`search_personal_references`, `search_saved_requests`)을 대상으로, mock 없이 **실제
`build_week04_agent()` + 실제 LLM(`openai/gpt-4.1-mini`) + 실제 OpenAI embedding API**를
호출하는 500개 테스트 케이스를 실행한 결과입니다. 1·2차 실행 시점에는 추가과제
(`search_conversation_messages`, `search_nana_memory`)가 TODO 스텁이라 테스트 범위에서
제외했으나, 3차 실행 시점에는 `search_conversation_messages`가 구현되어 tool 목록에 실제로
포함됩니다(`search_nana_memory`는 여전히 스텁). 이 500케이스 세트 자체는 여전히 메인과제
3개 tool만 겨냥하도록 설계되어 있어 세 번의 실행 모두 같은 기준으로 비교 가능합니다.

## 1. 방법론

- **실행 경로**: 앱이 실제로 쓰는 `fixed/week_agent_registry.py::run_active_week_agent(4, messages)`를
  그대로 재사용 — `agent.invoke({"messages": [...]})`를 호출하고 `extract_agent_events()`로
  tool_call/tool_result trace를 뽑는 앱과 동일한 코드 경로입니다.
- **데이터 격리**: 실제 `data/chroma`, `data/kanana_app.sqlite3`, `data/kanana_external_people.sqlite3`를
  임시 폴더에 복사한 뒤 `fixed.config.CONFIG.chroma_dir`/`app_db_path`/`external_db_path`를
  그 복사본으로 가리키도록 바꾸고(`object.__setattr__`, frozen dataclass 우회) 나서
  `student_parts` 모듈을 import했습니다. 학생의 실제 `data/`는 이 테스트로 전혀 변경되지
  않았습니다(아래 5절에서 무결성 확인).
- **케이스 구성(총 500개, 4개 카테고리)**:
  | 카테고리 | 개수 | 기대 tool |
  | --- | --- | --- |
  | `search_personal_references` 유도 질문 | 150 | `search_personal_references` |
  | `add_personal_reference` 유도 발화(개인 선호/특성 진술) | 100 | `add_personal_reference` |
  | `search_saved_requests` 유도 질문 | 150 | `search_saved_requests` |
  | control(다른 주제/다른 주차 의도, false-positive 측정용) | 100 | 없음(3개 tool 중 어느 것도 호출되면 안 됨) |
- **템플릿 기반 생성**: 각 카테고리마다 핵심 문장 pool(20~25개) × 어투 템플릿(4~6개)의
  조합으로 500개를 결정적으로 생성했습니다(코드: `gen_cases.py`, seed 고정).
- **동시 실행**: `ThreadPoolExecutor(max_workers=10)`으로 500건을 병렬 호출, 총 소요 시간 **319초(약 5.3분)**.
- **판정 기준**: `search_*`/`add_*` 카테고리는 trace의 `tool_call` 이벤트 중 기대 tool 이름이
  하나라도 있으면 pass, control 카테고리는 3개 대상 tool 중 어느 것도 호출되지 않으면 pass.

## 2. 결과 요약

| 카테고리 | Pass / Total | Pass율 |
| --- | --- | --- |
| `search_personal_references` | 124 / 150 | **82.7%** |
| `add_personal_reference` | 33 / 100 | **33.0%** |
| `search_saved_requests` | 73 / 150 | **48.7%** |
| control (false-positive 없음 확인) | 100 / 100 | **100.0%** |
| **전체** | 330 / 500 | **66.0%** |

- **예외(크래시) 발생 건수: 0/500.** 500건 모두 `agent.invoke()`가 예외 없이 끝났고
  (`run_active_week_agent`가 잡는 `trace_error`도 0건), 메인과제 3개 tool의 반환 JSON은
  500건 전부에서 계약된 top-level 키(`hits`/`rows`/`reference_backend`)를 정확히 지켰습니다.
  즉 **구현된 함수 자체(저장/검색 로직, JSON 계약)는 안정적**이며, 실패의 100%는
  "LLM이 애초에 그 tool을 고르지 않음"에서 발생했습니다.
- latency: 최소 1.2s / 중앙값 4.2s / 평균 6.2s / 최대 28.1s (건당, gpt-4.1-mini 기준).
- control 카테고리 false positive: **0건** — 무관한 대화(잡담, 인사, 다른 주차 일정 생성 요청 등)에서
  3개 대상 tool이 잘못 호출된 사례는 없었습니다.

## 2-1. 재실행 결과 (2026-07-25, 코드 변경 없음 — 재현성 확인)

같은 `student_parts/week04_retrieve_nanas_memory.py`(1절 실행 이후 diff 없음, `git diff` 확인됨)에
대해 동일한 방법론(1절)으로 500케이스를 한 번 더 실행했습니다. 목적은 66.0%라는 수치가 우연이
아니라 재현 가능한 패턴인지 확인하는 것이었습니다.

| 카테고리 | 1차 (07-22) | 2차 (07-25) |
| --- | --- | --- |
| `search_personal_references` | 82.7% (124/150) | 83.3% (125/150) |
| `add_personal_reference` | 33.0% (33/100) | 39.0% (39/100) |
| `search_saved_requests` | 48.7% (73/150) | 49.3% (74/150) |
| control | 100.0% (100/100) | 100.0% (100/100) |
| **전체** | **66.0%** (330/500) | **67.6%** (338/500) |
| 예외/`trace_error` 건수 | 0 | 0 |
| JSON 계약 위반 건수 | 0 | 0 |
| 소요 시간 | 319s | 187s |
| latency (median / avg) | 4.2s / 6.2s | 3.4s / 3.6s |

- 카테고리별 pass율이 전부 ±6%p 이내로 재현되었고, **버그 1~3에서 지목한 오분류 패턴(tool
  confusion 조합)도 1차와 거의 동일하게 나타났습니다**(`add_personal_reference` → 무응답/
  `save_structured_request`, `search_saved_requests` → `personal_list_saved_schedules`/
  `list_saved_requests`, `search_personal_references` → 저관련성 질의에서의 misroute).
  즉 아래 3절의 버그들은 프롬프트/LLM 판단의 우연한 변동이 아니라 **일관되게 재현되는
  tool-selection 문제**로 확인됩니다.
- 예외·`trace_error`·JSON 계약 위반은 2차에서도 0건으로, 구현 자체의 안정성 결론은 그대로
  유지됩니다.
- 2차 실행은 소요 시간이 187초로 1차(319초) 대비 짧았는데, 이는 코드 변경이 아니라 실행
  시점의 API 응답 속도 편차(median 4.2s→3.4s)로 보입니다.
- 2차에서 쓴 격리 데이터 복사본도 테스트 종료 후 삭제했고, 실제 `data/`의 row 개수
  (`structured_requests=5, schedules=3, todos=1, reminders=1`)는 1차·2차 전후로 변함이
  없음을 확인했습니다.

## 2-2. 3차 실행 결과 (2026-07-25, 코드 변경 있음 — 버그 수정 검증)

1·2차 실행 이후 `student_parts/week04_retrieve_nanas_memory.py`가 실제로 수정되었습니다
(`git diff` 기준 주요 변경):

- `week04_prompt_parts()`의 `*week03_prompt_parts()` 중복 제거(버그 4)
- tool 사용 지침을 서술문에서 명령문으로 재작성 — 특히 "사용자가 개인 정보를 진술하면
  **반드시** `add_personal_reference`를 호출한다. 호출하지 않은 채로 '저장했다'고 답하지
  않는다"(버그 1 직접 타겟), "단순 목록 나열인 Week3 `personal_list_saved_schedules`와
  달리, 내용 검색이 필요할 때만 `search_saved_requests`를 쓴다"(버그 2 직접 타겟)를 명시
- `search_conversation_messages_dict`/`_rows`/tool 구현(추가과제 일부, 이번 500케이스
  범위 밖)

같은 500케이스·같은 방법론으로 3차 실행한 결과이며, 이번엔 케이스별 원본 trace(JSONL)를
보존해 정확한 수치 비교가 가능합니다.

| 카테고리 | 1차 (07-22) | 2차 (07-25, 무변경) | 3차 (07-25, 코드 수정 후) |
| --- | --- | --- | --- |
| `search_personal_references` | 82.7% (124/150) | 83.3% (125/150) | 82.7% (124/150) |
| `add_personal_reference` | 33.0% (33/100) | 39.0% (39/100) | **72.0% (72/100)** |
| `search_saved_requests` | 48.7% (73/150) | 49.3% (74/150) | **64.0% (96/150)** |
| control | 100.0% (100/100) | 100.0% (100/100) | 100.0% (100/100) |
| **전체** | **66.0%** (330/500) | **67.6%** (338/500) | **78.4%** (392/500) |
| 예외/`trace_error`/JSON 계약 위반 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| latency (median / avg) | 4.2s / 6.2s | 3.4s / 3.6s | 3.2s / 3.4s |

1~2차 사이의 변동(±6%p 이내)이 노이즈였던 것과 달리, 이번 3차는 **`add_personal_reference`
+33~39%p, `search_saved_requests` +15%p** 로 두 카테고리 모두 100 표본 기준 95% 신뢰구간
(각각 약 ±9%p, ±8%p)을 크게 벗어나는 이동이라 통계적으로 유의미한 개선입니다. 코드에서
직접 겨냥한 버그와 정확히 일치하는 카테고리가 개선되었다는 점도 이게 우연이 아니라
프롬프트 수정의 효과임을 뒷받침합니다.

### [3차 재검증] 버그 1 (`add_personal_reference` 저트리거) — 상당히 개선, 완전 해결은 아님

72/100 pass. 남은 28건 실패 내역:

- 16건: 여전히 아무 tool도 호출되지 않음(1차 32건 → 3차 16건, 절반으로 감소)
- 11건: 여전히 `save_structured_request`로 오분류(1차 35건 → 3차 11건)
- 1건: `extract_schedule_request` + `save_structured_request` 동시 호출

방향은 뚜렷이 개선됐지만, "저장하겠다고 말만 하고 tool을 안 부르는" 케이스가 16건 남아있어
1절에서 지적한 "거짓 확인" 문제가 완전히 사라지지는 않았습니다.

### [3차 재검증] 버그 2 (`search_saved_requests`의 Week3 tool 혼선) — 상당히 개선, 완전 해결은 아님

96/150 pass. 남은 54건 실패 내역:

- 31건: `list_saved_requests` 호출(1차 26건 대비 오히려 소폭 증가)
- 23건: `personal_list_saved_schedules` 호출(1차 50건 → 3차 23건, 절반 이하로 감소)

`personal_list_saved_schedules`로의 오분류는 크게 줄었지만, `list_saved_requests`
(Week3의 또 다른 조회 tool)로의 혼선은 오히려 살짝 늘었습니다 — 프롬프트가 두 Week3
tool 중 하나만 명시적으로 언급했기 때문일 가능성이 있습니다.

### 새로 관찰된 패턴 — `search_personal_references`가 이번엔 `search_saved_requests`로 샘

`search_personal_references` 카테고리 자체의 pass율은 82.7%로 1차와 동일하지만, 실패
26건의 내부 구성이 달라졌습니다: 1~2차엔 실패가 여러 tool(`list_saved_requests`,
`personal_list_saved_schedules`, `extract_schedule_request` 등)에 고르게 흩어져
있었는데, 3차에는 **19/26건이 전부 `search_saved_requests`로 쏠렸습니다.**
`search_saved_requests`의 지침이 이번에 훨씬 명확해지면서, 원래 `search_personal_references`가
맡아야 할 애매한 케이스 일부까지 끌어당기는 부작용으로 보입니다 — 한쪽 tool의 지침을
명확히 하면 다른 tool과의 경계가 오히려 흔들릴 수 있다는 사례입니다.

## 2-3. 4차 실행 결과 (2026-07-25, 코드 추가 수정 — control false-positive 리스크 검증)

3차 이후 `week04_prompt_parts()`가 한 번 더 수정되었습니다. 핵심 변화:

- "기억·저장·조회·검색과 조금이라도 관련된 질문이면 추측하지 말고 먼저 tool을 호출한다"는
  일반 지침 추가
- 저관련성 질문에 대한 대응이 3차의 "관련성이 매우 낮으면 먼저 되묻는다"에서
  **"되묻기 전에 가장 알맞은 검색 tool을 먼저 한 번 시도한다. 인사·감사·잡담에만 tool을
  호출하지 않는다"** 로 바뀜 — tool을 더 적극적으로 호출하는 방향
- `search_conversation_messages` 호출 지침도 "망설이지 말고 호출한다"로 더 단정적으로 변경

이 변화는 recall(진짜 필요할 때 tool을 부르는 비율)을 높이는 대신 precision(관련 없는데도
tool을 잘못 부르는 비율)을 해칠 위험이 있어, control 카테고리(100건, 대상 tool이 전혀
필요 없는 대화)의 false-positive 여부를 특히 주의 깊게 확인했습니다.

| 카테고리 | 1차 | 2차 | 3차 | 4차 |
| --- | --- | --- | --- | --- |
| `search_personal_references` | 82.7% | 83.3% | 82.7% | 83.3% (125/150) |
| `add_personal_reference` | 33.0% | 39.0% | 72.0% | **77.0% (77/100)** |
| `search_saved_requests` | 48.7% | 49.3% | 64.0% | **74.7% (112/150)** |
| control (false-positive 없음) | 100.0% | 100.0% | 100.0% | **100.0% (100/100)** |
| **전체** | **66.0%** | **67.6%** | **78.4%** | **82.8% (414/500)** |
| 예외/`trace_error`/JSON 계약 위반 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| latency (median/avg) | 4.2s/6.2s | 3.4s/3.6s | 3.2s/3.4s | 3.1s/3.2s |

**결론부터: 우려했던 부작용은 나타나지 않았습니다.** "애매하면 되묻지 말고 tool부터
시도하라"는 더 공격적인 지침으로 바뀌었는데도 control 카테고리는 4번의 실행 모두
100/100을 유지했습니다. 인사·잡담·다른 주차 일정 생성 요청 등에서 대상 3개 tool이나
새로 구현된 `search_conversation_messages`가 오발화된 사례는 이번에도 0건입니다. 대신
recall 쪽 지표(`add_personal_reference`, `search_saved_requests`)만 순수하게 개선됐습니다.

### 3차 → 4차 세부 변화

- `add_personal_reference` 실패 23건: `<none>` 13건(3차 16건에서 소폭 감소),
  `save_structured_request` 10건(3차 11건과 거의 동일) — "저장했다고 답만 하고 tool
  안 부름" 문제가 조금 더 줄었지만 여전히 남아 있습니다.
- `search_saved_requests` 실패 38건: `list_saved_requests` 23건(3차 31건에서 감소),
  `personal_list_saved_schedules` 15건(3차 23건에서 감소) — 두 Week3 tool로의 혼선이
  **둘 다** 동시에 줄었습니다. 3차에서 `personal_list_saved_schedules`만 명시적으로
  언급했던 프롬프트가 4차에서 일반화(`단순 목록 나열`)되면서 `list_saved_requests` 쪽
  혼선도 같이 줄어든 것으로 보입니다.
- `search_personal_references`는 여전히 83% 선에서 정체 — 실패 25건 중 21건이 여전히
  `search_saved_requests`로 쏠려 있어(3차 19건과 비슷한 규모), 2-2절에서 지적한
  "search_saved_requests 쪽 경계가 넓어지며 옆 tool을 잠식하는" 현상이 3~4차에 걸쳐
  일관되게 남아 있는 잔여 이슈입니다.

## 2-4. 5차 실행 결과 (2026-07-25, 코드 추가 수정 — 트레이드오프 확인)

4차 이후 `week04_prompt_parts()`가 다시 수정되었습니다. 이번엔 정확히 2-3절에서 지목한
잔여 문제("성향/취향 질문이 search_saved_requests로 잠식됨")를 직접 겨냥해 다음 문장이
추가됐습니다: *"사용자의 성향·취향 같은 개인 특성은 이 tool(search_saved_requests)이
아니라 search_personal_references로 보낸다"*, *"이는 일정·할 일이 아니므로
save_structured_request가 아니라 add_personal_reference로 저장"*.

| 카테고리 | 1차 | 2차 | 3차 | 4차 | 5차 |
| --- | --- | --- | --- | --- | --- |
| `search_personal_references` | 82.7% | 83.3% | 82.7% | 83.3% | **85.3% (128/150)** |
| `add_personal_reference` | 33.0% | 39.0% | 72.0% | 77.0% | **96.0% (96/100)** |
| `search_saved_requests` | 48.7% | 49.3% | 64.0% | 74.7% | **54.7% (82/150) ▼** |
| control (false positive 0건) | 100.0% | 100.0% | 100.0% | 100.0% | **100.0% (100/100)** |
| **전체** | **66.0%** | **67.6%** | **78.4%** | **82.8%** | **81.2% (406/500) ▼** |
| latency (median/avg) | 4.2s/6.2s | 3.4s/3.6s | 3.2s/3.4s | 3.1s/3.2s | 3.4s/3.6s |

**의도한 수정은 정확히 먹혔지만, 그 대가로 다른 카테고리가 크게 후퇴했습니다.**

- `add_personal_reference`: 77% → **96%**, 사실상 거의 다 고쳐졌습니다. 남은 실패는
  단 4건("tool 미호출" 3건, `save_structured_request` 오분류 1건)뿐입니다.
- `search_personal_references`: 83.3% → **85.3%**, `search_saved_requests`로의 유출도
  21건 → 17건으로 줄어 의도한 방향대로 움직였습니다.
- `search_saved_requests`: 74.7% → **54.7%로 급락** (112건 → 82건, **30건 감소**).
  실패 내역을 보면 `list_saved_requests` 오분류가 23건 → 42건으로, `personal_list_saved_schedules`
  오분류가 15건 → 26건으로 **둘 다 거의 두 배**가 됐습니다.

즉 "성향/취향은 search_saved_requests가 아니다"라는 규칙을 강하게 넣은 부작용으로, 모델이
`search_saved_requests`를 호출하는 것 자체에 더 소극적으로 바뀌어 **원래 이 tool이
호출됐어야 할 진짜 일정/할 일/알림 질문에서도 Week3 tool로 더 많이 새어나갔습니다.**
전체 pass율도 82.8% → 81.2%로 소폭 하락했는데, 이는 `search_saved_requests`의 후퇴 폭
(-20%p, 150건 기준)이 다른 두 카테고리의 개선 폭을 상쇄하고 남았기 때문입니다.

**이건 이번 세션 전체에서 반복적으로 관찰된 패턴입니다**: 한 tool의 경계를 명확히 하는
지시문을 추가하면 그 tool의 정확도는 오르지만, 인접한 tool의 정확도가 대신 떨어집니다
(3→4차의 `search_personal_references`↔`search_saved_requests`, 이번 4→5차의
`search_saved_requests`↔`{search_personal_references, add_personal_reference}`).
세 tool의 경계 지침을 개별적으로 하나씩 강화하는 방식으로는 계속 이런 시소 현상이
반복될 가능성이 높고, 세 tool의 판단 기준을 **한 번에 서로 배타적으로** 정의하는 방향의
프롬프트 재설계가 필요해 보입니다.

## 2-5. 6차 실행 결과 (2026-07-25, 프롬프트 전면 재작성 — 개별 patch에서 라우팅 표 방식으로)

2-4절 끝에서 "세 tool의 판단 기준을 한 번에 상호 배타적으로 재설계"할 필요가 있다고
적었는데, 5차 이후 정확히 그 방향으로 `week04_prompt_parts()`가 다시 쓰였습니다. 개별
tool 설명을 하나씩 patch하는 대신, "질문이 무엇에 대한 것인가(개인 특성 / 일정·약속 /
과거 대화)라는 단 하나의 축으로만 tool을 정한다"는 원칙과 (1)~(5)번 라우팅 표를
명시했습니다.

| 카테고리 | 1차 | 2차 | 3차 | 4차 | 5차 | 6차 |
| --- | --- | --- | --- | --- | --- | --- |
| `search_personal_references` | 82.7% | 83.3% | 82.7% | 83.3% | 85.3% | **74.7% ▼** |
| `add_personal_reference` | 33.0% | 39.0% | 72.0% | 77.0% | 96.0% | **61.0% ▼▼** |
| `search_saved_requests` | 48.7% | 49.3% | 64.0% | 74.7% | 54.7% | **63.3%** |
| control (false positive 0건) | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| **전체** | **66.0%** | **67.6%** | **78.4%** | **82.8%** | **81.2%** | **73.6% ▼** |
| latency (median/avg/max) | 4.2/6.2/28.1s | 3.4/3.6/17.8s | 3.2/3.4/9.8s | 3.1/3.2/10.4s | 3.4/3.6/12.2s | 3.2/3.5/**71.2s** |

**제가 앞서 제안한 방향이 틀렸다는 걸 데이터로 확인했습니다.** 라우팅 표 방식은
`search_saved_requests`만 소폭 개선(54.7%→63.3%, 다만 4차의 74.7%엔 여전히 못 미침)
시켰을 뿐, 나머지 두 카테고리는 모두 5차 대비 크게 후퇴했습니다:

- `add_personal_reference`: 96.0% → **61.0%** (39건 실패, 그중 33건이 "tool 호출 없이
  대화로만 응답"). 5차에서 거의 해결됐던 "저장했다고 말만 하고 tool을 안 부르는" 문제가
  거의 원점(1차 수준)으로 되돌아갔습니다. 5차 프롬프트는 add_personal_reference 전용으로
  "tool을 호출하지 않은 채로 저장했다고 답하지 않는다"를 못박았는데, 6차는 이 문장을
  5개 tool 공통의 일반 규칙 한 줄("해당 tool을 호출하지 않은 채로 '저장했다'·'찾았다'·
  '기억하겠다'고 답하지 않는다")로 뭉뚱그리면서 개별 tool에 대한 압박이 약해진 것으로
  보입니다.
- `search_personal_references`: 85.3% → **74.7%**, `search_saved_requests`로의 유출이
  17건 → **31건으로 오히려 2배 가까이 증가**했습니다. "일정·약속의 구체적 내용"과
  "개인 특성"을 표로 나눠 구분해줬는데도 혼선이 줄지 않고 늘었습니다.
- latency 이상치: 71.2초짜리 케이스가 하나 발생(다른 실행에서는 최대 10~28초 수준).
  라우팅 표가 길어지면서 모델이 판단에 더 오래 걸리는 케이스가 생긴 것으로 추정되나,
  1건뿐이라 확정하긴 이릅니다.

**시사점**: "표로 명확히 규칙을 정리하면 모델이 더 잘 따를 것"이라는 가설은 이번
케이스에서는 틀렸습니다. 오히려 (a) 각 tool에 대한 개별적이고 구체적인 명령("반드시
호출한다", "~라고 답하지 않는다")이 공통 규칙으로 일반화되면서 힘을 잃었고, (b) 표
형식 자체가 프롬프트 길이를 늘려 관련 없는 정보가 판단을 방해했을 가능성이 있습니다.
지금까지의 6번 실행을 종합하면 **4차 시점의 프롬프트(전체 82.8%, 카테고리별 최저
77.0%)가 지금까지 실험한 버전 중 가장 균형 잡힌 결과**였고, 5차는 `add_personal_reference`
단일 카테고리 최고점(96%)을 냈지만 `search_saved_requests`를 크게 희생했습니다. "모든
카테고리를 동시에 90%대로 끌어올리는" 프롬프트는 아직 6번의 시도 중에는 나오지 않았습니다.

## 3. 발견된 버그 / 이슈 (1차 실행 시점 기록 — 수정 여부는 각 항목 하단 갱신 참고)

> 아래 4개는 모두 1차 실행(2026-07-22) 시점에 "수정 보류, 기록만" 조건으로 작성됐습니다.
> 2026-07-25 코드 수정 이후 상태는 각 항목 끝에 갱신했고, 정량적 근거는 2-2절 참고.

### 버그 1 — [Critical] `add_personal_reference`가 67%의 경우 호출되지 않고, 그런데도 "저장했다"고 답변함

100개 중 67개(67%)가 fail. 세부 내역:

- **35건**: `add_personal_reference` 대신 Week2/3의 `save_structured_request`가 호출됨.
  이 tool은 일정/할일/알림(`kind`)을 위한 것이라 개인 선호 진술을 넣으면 `kind: "unknown"`
  또는 잘못 추론된 `kind: "reminder"`로 `structured_requests` 테이블에 저장됩니다.
  예:
  ```
  RA001 "이거 저장해줘: 나는 스트레스 받을 때 산책을 하면 도움이 돼."
    -> save_structured_request(kind="unknown", title=None, reason="사용자가 스트레스 해소 방법으로 산책을 언급함", ...)
  RA007 "메모 좀 남겨줘. 나는 스트레스 받을 때 산책을 하면 도움이 돼."
    -> save_structured_request(kind="reminder", title="스트레스 받을 때 산책하기", ...)
  ```
  같은 발화가 케이스마다 `kind`가 `unknown`/`reminder`로 오락가락하고, `reminders` 테이블에는
  본래 취지(알림 시각)와 무관한 "선호 진술"이 알림처럼 끼어들어갑니다.

- **32건**: 아예 **어떤 tool도 호출되지 않음** — 그럼에도 assistant 응답은
  "기억해 두겠습니다", "잘 저장해 두었습니다"처럼 **마치 저장이 된 것처럼 답변**합니다.
  예:
  ```
  RA002 "참고로 나는 문서 리뷰는 항상 퇴근 전에 몰아서 하는 편이야."
    -> tool 호출 없음. 답변: "...기억해 두겠습니다. 일정 관리에 참고하도록 하겠습니다."
  RA010 "참고로 나는 점심 약속은 웬만하면 화요일이나 목요일에 잡아."
    -> tool 호출 없음. 답변: "...참고하겠습니다. 앞으로 일정 조율 시 이 점을 반영하도록 하겠습니다."
  ```
  이건 **사용자 신뢰를 깨는 실질적 정합성 버그**입니다 — 사용자는 정보가 저장됐다고 믿지만
  `search_personal_references`로 나중에 찾을 방법이 없습니다(애초에 어디에도 안 쓰였으므로).

- 원인 추정: `week04_prompt_parts()`의 `add_personal_reference` 사용 시점 지시문(
  "사용자의 특성, 개인 정보, 선호, 비선호 등을 입력 시 저장")이 서술적이라, LLM이
  "지금 당장 tool을 호출해야 한다"는 명령으로 받아들이지 않고 대화 맥락으로만 흡수하는
  경우가 많아 보입니다. Week3 리뷰에서 이미 짚었던 "서술문 vs 지시문" 이슈와 같은 패턴입니다.

### 버그 2 — [Major] `search_saved_requests`가 51%의 경우 Week3 조회 tool로 새는 문제

150건 중 77건(51.3%) fail, 전부 **틀린 tool이 아니라 "다른 정상 tool"이 대신 호출된 경우**입니다:

- 50건: `personal_list_saved_schedules` (Week3) 호출
- 26건: `list_saved_requests` (Week3) 호출
- 1건: 둘 다 호출

`week04_prompt_parts()`에 "Week3 personal_list_saved_schedules와의 구분" 문장이 이미
있음에도, 실제로는 절반 이상의 케이스에서 LLM이 Week3 tool을 선택합니다. 예:

```
SS011 "팀 회의라는 이름으로 저장된 일정 있어?" -> personal_list_saved_schedules 호출
SS023 "7월 23일에 잡아둔 일정 검색해줘"        -> personal_list_saved_schedules 호출
```

두 tool 다 SQLite `schedules`/`structured_requests`를 보므로 답변 자체는 대체로 맞게
나오지만(위 예시들의 최종 답변은 실제로 정확함), Week4 과제가 요구하는 "출처별 tool 분리"
의도와는 다르게 동작하고 있다는 뜻입니다. 즉 **최종 답변 품질로는 안 드러나고, trace를
봐야만 드러나는 종류의 회귀**입니다.

### 버그 3 — [Moderate] `search_personal_references` 저관련성 질의가 Week1-3 tool로 오분류 (17%)

150건 중 26건(17.3%) fail. 개인 참고자료에 없는 정보(생일, MBTI, 좋아하는 색 등)를 묻는
저관련성 질문들이 `list_saved_requests`/`search_saved_requests`/`personal_list_saved_schedules`로
새는 것은 어느 정도 예상 범위지만, 2건은 명백한 오분류입니다:

```
RS113 "혹시 점심시간에 회의 잡아도 괜찮을까?" -> extract_schedule_request 호출
```

`extract_schedule_request`는 Week2의 "일정 생성 요청에서 구조화된 필드를 뽑는" tool인데,
이 질문은 일정을 잡아달라는 요청이 아니라 참고자료 검색성 질문입니다. 의미상 완전히
다른 tool이 선택된 경우입니다.

> **[3차 갱신]** 3차 실행에서도 이 카테고리 pass율은 82.7%로 그대로지만, 실패 사유의
> 구성은 바뀌었습니다 — 2-2절 "새로 관찰된 패턴" 참고. `search_saved_requests`의 지침이
> 명확해진 부작용으로 실패가 `search_saved_requests` 한 곳으로 쏠렸습니다.

### 버그 4 — [Cosmetic] `week04_prompt_parts()`에 `*week03_prompt_parts()`가 중복 포함

`student_parts/week04_retrieve_nanas_memory.py`의 `week04_prompt_parts()` 반환 리스트를
보면:

```python
return [
    *week03_prompt_parts(),
    
*week03_prompt_parts(),
"add_personal_reference 사용 시점 설명 문장 ...",
...
```

`*week03_prompt_parts()`가 **두 번** 들어 있습니다. 기능이 깨지지는 않지만(같은 지시문이
system prompt에 중복으로 실리는 것뿐), 매 요청마다 Week1~3 프롬프트 조각 전체가 두 번
전송되어 불필요하게 프롬프트 토큰을 낭비합니다. (1차 실행 시점에는 요청에 따라 수정하지
않고 기록만 남겼습니다.)

> **[3차 갱신] 수정 완료로 확인됨.** 2026-07-25 코드 수정으로 `week04_prompt_parts()`가
> 통째로 재작성되면서 중복 라인이 제거됐습니다(`git diff` 확인).

### 참고 — 추가과제(스텁) 현황 (1차 실행 시점 기록)

1차 실행 시점에는 `search_conversation_messages_dict`, `search_conversation_message_rows`,
`search_conversation_messages`(tool), `search_nana_memory`(tool) 4개가 모두 `...`
(Ellipsis) 스텁 상태였습니다. 이번 500케이스는 메인과제 3개 tool만 대상으로 했으므로
이 4개는 호출 대상에서 제외했습니다.

> **[3차 갱신]** `search_conversation_messages_dict`/`_rows`/tool 3개는 2026-07-25
> 코드 수정으로 구현되었고, 3차 실행 시점에는 tool 목록에 실제로 포함되어 있었습니다
> (다만 500케이스 세트 자체는 여전히 이 tool을 겨냥하지 않아 별도 검증은 안 됨 — control
> 카테고리 100건에서 이 tool의 false positive는 0건으로 확인). `search_nana_memory`는
> 여전히 스텁입니다.

## 4. 정상 동작 확인된 부분

- **JSON 계약 100% 준수**: 500건 중 tool이 실제로 호출된 모든 경우에서
  `search_personal_references` → `{"hits": [...]}`, `search_saved_requests` → `{"rows": [...]}`,
  `add_personal_reference` → `{"reference_backend": {...}, "reference": {...}}` 최상위 키가
  한 번의 예외도 없이 지켜졌습니다.
- **hit 구조 정합성**: `search_personal_reference_hits`가 반환하는 `id`/`content`/`distance`/
  `metadata.title`/`metadata.tags`가 항상 채워져 있었고, `tags`는 콤마 문자열 → 리스트
  round-trip이 정상 동작했습니다.
- **false positive 0건**: 잡담·인사·다른 주차 일정 생성 요청 100건에서 대상 3개 tool이
  잘못 호출된 적이 없습니다 — "관련 없으면 지어내지 않는다"는 프롬프트 지시가 최소한
  "엉뚱하게 tool을 호출하지는 않는" 수준에서는 잘 지켜지고 있습니다.
- **크래시/미처리 예외 0건**: PROXY_TOKEN, embedding API, SQLite 동시 접근(쓰기 포함,
  10-worker 병렬) 전 구간에서 처리되지 않은 예외가 없었습니다.

## 5. 데이터 무결성

여섯 번의 실행(1차 07-22, 2차~6차 07-25) 모두 `data/chroma`, `data/kanana_app.sqlite3`,
`data/kanana_external_people.sqlite3`의 임시 복사본에 대해서만 실행되었고, 실제 `data/`는
건드리지 않았습니다 — 매 실행 전후로 `structured_requests=5, schedules=3, todos=1,
reminders=1` row 개수가 그대로임을 확인했습니다. 각 실행이 남긴 임시 복사본(예: 1차의
33건 `add_personal_reference` 성공 호출 + 35건의 오분류된 `save_structured_request` 호출이
남긴 더미 데이터)은 매번 삭제했습니다. 3차 실행부터는 집계용 원본 trace(`results_500.jsonl`)
자체는 삭제하지 않고 스크래치 디렉터리에 보존해, 이후 케이스 단위 재검증이 가능하도록
했습니다.

## 6. 재현 방법

케이스 생성/실행 스크립트(`gen_cases.py`, `run_cases.py`, `analyze.py`)는 이번 실행 전용
스크래치 코드로 작성되어 저장소에는 포함하지 않았습니다. 필요 시 같은 방법론(1절)으로
재작성해 재현할 수 있습니다 — 핵심은 `CONFIG.chroma_dir`/`app_db_path`를 임시 복사본으로
패치한 뒤 `fixed.week_agent_registry.run_active_week_agent(4, [{"role": "user", "content": prompt}])`를
호출하고 `result.trace["events"]`의 `tool_call` 이벤트를 검사하는 것입니다. 같은 `gen_cases.py`
(고정 시드)를 재사용하면 세 번의 실행과 동일한 500개 프롬프트로 비교할 수 있습니다.
