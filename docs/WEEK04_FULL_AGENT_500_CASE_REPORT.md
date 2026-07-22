# Week 4 실제 Agent 500케이스 테스트 보고서

`student_parts/week04_retrieve_nanas_memory.py`의 메인과제 3개 tool(`add_personal_reference`,
`search_personal_references`, `search_saved_requests`)을 대상으로, mock 없이 **실제
`build_week04_agent()` + 실제 LLM(`openai/gpt-4.1-mini`) + 실제 OpenAI embedding API**를
호출하는 500개 테스트 케이스를 실행한 결과입니다. 추가과제(`search_conversation_messages`,
`search_nana_memory`)는 아직 TODO 스텁이라 이번 테스트 범위에서 제외했습니다.

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

## 3. 발견된 버그 / 이슈 (수정은 보류, 목록만 기록)

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
전송되어 불필요하게 프롬프트 토큰을 낭비합니다. (요청에 따라 이번에는 수정하지 않고
기록만 남깁니다.)

### 참고 — 추가과제(스텁) 현황 (버그 아님, 미구현 상태 기록)

`search_conversation_messages_dict`, `search_conversation_message_rows`,
`search_conversation_messages`(tool), `search_nana_memory`(tool) 4개는 모두 `...`
(Ellipsis) 스텁 상태입니다. 이번 500케이스는 메인과제 3개 tool만 대상으로 했으므로
이 4개는 호출 대상에서 제외했습니다.

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

테스트는 `data/chroma`, `data/kanana_app.sqlite3`, `data/kanana_external_people.sqlite3`의
임시 복사본에 대해서만 실행되었고, 실제 `data/`는 건드리지 않았습니다. 테스트 종료 후
임시 복사본(500개 케이스 중 33건의 `add_personal_reference` 성공 호출 + 35건의 오분류된
`save_structured_request` 호출이 남긴 더미 데이터 포함)은 삭제했습니다.

## 6. 재현 방법

케이스 생성/실행 스크립트(`gen_cases.py`, `run_cases.py`, `analyze.py`)는 이번 실행 전용
스크래치 코드로 작성되어 저장소에는 포함하지 않았습니다. 필요 시 같은 방법론(2절)으로
재작성해 재현할 수 있습니다 — 핵심은 `CONFIG.chroma_dir`/`app_db_path`를 임시 복사본으로
패치한 뒤 `fixed.week_agent_registry.run_active_week_agent(4, [{"role": "user", "content": prompt}])`를
호출하고 `result.trace["events"]`의 `tool_call` 이벤트를 검사하는 것입니다.
