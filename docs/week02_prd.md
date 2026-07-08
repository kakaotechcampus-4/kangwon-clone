# Week 2 PRD — 자연어 요청 구조화 (Structured Output)

대상 파일: [`student_parts/week02_structure_natural_language_requests.py`](../student_parts/week02_structure_natural_language_requests.py)

## 배경

Week 1은 "실행"의 문제였다 — LLM이 로컬 함수(`personal_create_schedule` 등)를 호출해서 실제로 일정을 만들고 조회하고 지웠다. Week 2는 "출력 형식"의 문제다 — Nana의 최종 답변이 자유 문장이 아니라, 앱이 바로 다음 단계(Week 3 저장)에서 그대로 쓸 수 있는 고정된 Pydantic 객체(`StructuredRequestBatch`)여야 한다.

## 목표

사용자의 자연어 요청 또는 Week 1 tool이 반환한 JSON을, `kind`로 종류를 구분하는 `StructuredRequestBatch` 구조로 항상 변환해서 반환한다.

## 범위 (In Scope)

- `StructuredRequest` / `StructuredRequestBatch` Pydantic 스키마 정의
- `week02_tools()`, `week02_prompt_parts()`, `week02_system_prompt()`, `build_week02_agent()` 구현
- `./run.sh --week2`로 정상 동작 확인

## 범위 아님 (Out of Scope)

- SQLite 저장, RAG, 외부 멤버 일정 조율 — 다음 주차 대상
- `_coerce_structured_request`, `extract_structured_request`, `extract_schedule_request` — docstring에 "이후 회차에서 사용할 예약 함수"로 명시된 placeholder, 이번 주 TODO 아님

## 요구사항

### FR1. `StructuredRequest` 스키마
- `kind`: `RequestKind` Literal (`personal_schedule` / `group_schedule` / `todo` / `reminder` / `unknown`)
- `title`, `date`, `start_time`, `end_time`: `str | None`, 기본값 `None`
- `members`: `list[str]`, `default_factory=list`
- `priority`, `reason`: `str | None`, 기본값 `None`
- `original_text`: `str`, 기본값 `""`
- 각 필드에 LLM이 이해할 수 있는 한국어 `Field(description=...)` 부여
- **불확실한 값을 억지로 채우지 않는다** — 확실하지 않으면 `None`/빈 list가 정답

### FR2. `StructuredRequestBatch` 스키마
- `requests`: `list[StructuredRequest]`, `default_factory=list` — 요청이 하나뿐이어도 리스트 형태 유지
- `base_date`: `str`, `default_factory=current_app_date_iso` — 상대 날짜 해석 기준일

### FR3. `week02_tools()`
- Week 1 tool 목록(`week01_tools()`)을 그대로 노출

### FR4. `week02_prompt_parts()` / `week02_system_prompt()`
- `week01_prompt_parts()` 위에 다음을 누적:
  - 자연어를 `StructuredRequest` 필드로 구조화하라는 지시
  - Week 1 tool 결과(`personal_create_schedule`의 `created_schedule`)를 받았으면 재호출 없이 그 JSON을 읽어 구조화하라는 지시
  - SQLite 저장/RAG/외부 멤버 조율은 이번 주 범위가 아니라는 명시

### FR5. `build_week02_agent()`
- `CONFIG.has_openai_key` 없으면 `RuntimeError("PROXY_TOKEN이 .env에 필요합니다.")`
- 전역 `_WEEK02_AGENT` 캐시, 없을 때만 `create_agent(model=chat_model(), tools=week02_tools(), response_format=StructuredRequestBatch, system_prompt=week02_system_prompt())`

## 구현 순서

1. `StructuredRequest` → 2. `StructuredRequestBatch` → 3. `week02_tools()` → 4. `week02_prompt_parts()` → 5. `week02_system_prompt()` → 6. `build_week02_agent()`

(스키마가 먼저 있어야 나머지가 그걸 참조할 수 있고, prompt는 tools 뒤에, agent 조립은 맨 마지막.)

## 완료 기준 (Acceptance Criteria)

`./run.sh --week2` 실행 후:

- [ ] "다음 주 화요일 오후 3시에 철수랑 회의 잡아줘" 입력 시 최종 답변이 `StructuredRequestBatch` 형태의 `structured_response`로 나온다
- [ ] `kind`가 요청 종류(personal_schedule/group_schedule/todo/reminder/unknown)에 맞게 분류된다
- [ ] 확실하지 않은 필드는 `None`/`[]`로 남아 있고, 모델이 근거 없이 값을 지어내지 않는다
- [ ] 개인 일정 생성 요청("일정 만들어줘")에서는 Week 1의 `personal_create_schedule` 결과(`created_schedule`)를 읽어 구조화 근거로 쓰고, 같은 값을 다시 묻지 않는다
- [ ] 애매한 문장("음... 그거 있잖아")은 `kind="unknown"`으로 안전하게 분류된다

## 리스크

- `Field(description=...)`를 과하게 구체적으로 쓰면 모델이 실제 근거 없이 값을 채워 넣을 위험이 있다 → 시스템 프롬프트에 "확실하지 않으면 None/빈 list를 유지하라"는 지시를 명시적으로 넣어 상쇄한다.
