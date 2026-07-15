# 1~3주차 학습 정리 (2026-07-15)

Kanana Schedule Agent 과제를 진행하며 Claude와 나눈 대화를 정리한 개인 학습 노트. 전체 아키텍처 흐름과 3주차(`student_parts/week03_build_nanas_logbook.py`) 구현 과정, 그 과정에서 겪은 디버깅 사례를 담는다.

## 0. 큰 그림 한 줄

**kanana AI agent = "AI가 스스로 생각해서 알아서 행동한다."**
1~6주차는 이 한 문장을 한 겹씩 확장해나가는 과정이다.

## 1. 1~6주차 아키텍처

| 주차 | 핵심 문제 | 이번 주에 새로 생기는 것 |
|---|---|---|
| **1주차** | "실행" — LLM이 함수를 직접 호출해서 뭔가 하게 만들기 | tool calling, 휘발성 메모리(`PERSONAL_SCHEDULES` 리스트) |
| **2주차** | "출력 형식" — 자유 문장이 아니라 앱이 읽을 고정된 구조로 답하기 | `StructuredRequestBatch` (Pydantic structured output) |
| **3주차** | "영속성" — 구조화된 결과가 앱을 꺼도 안 사라지게 | SQLite 저장 (`args_schema`로 tool 입력 검증 → `structured_requests`=원본 감사 로그 + `schedules`/`todos`/`reminders`=정규화 테이블) |
| **4주차** | "기억의 종류 나누기" — 자유 텍스트 기억 vs 구조화된 기억은 검색 방식이 다름 | `search_rag_memory`(ChromaDB, 의미 기반 검색) vs `search_sqlite_requests`(3주차 DB 검색) |
| **5주차** | "접근 경로 분리" — agent 코드가 DB를 직접 안 읽게 | 로컬 MCP server가 SQLite를 tool 프로토콜 뒤로 숨김 |
| **6주차** | "여러 사람 조율" — 내 일정만으론 안 되고 팀원 일정까지 종합 | supervisor(delegate만) + `nana_agent`(내 일정/RAG) + `kana_agent`(MCP로 남의 일정 종합) |

핵심 포인트:
- **2주차**는 "텍스트로 하면 부정확해서"가 아니라, **"자유 문장 답변은 다음 단계(3주차 저장)가 못 읽기 때문"**에 구조화가 필요했던 것.
- **4주차의 "기억 검색"**은 지금 대화 안에서 슬롯을 차근차근 채우는 것과는 다르다. 같은 대화 안에서 이전 메시지를 참고하는 건 이미 1주차부터 되는 기능(`fixed/agent_runtime.py`가 매 turn마다 대화 history 전체를 다시 LLM에 넣어줌). 4주차는 **"지금 이 대화의 메시지 히스토리에 없는"** 다른 대화/과거 기록을 검색 tool로 끌어오는 것.
- **5주차**는 4주차와 기능은 같고 "누가 그 검색을 수행하냐"는 구조만 바뀜 (agent 코드 내부 → 별도 MCP 서버).

## 2. 채팅 로그 vs 구조화 데이터 (둘 다 SQLite, 같은 파일 다른 테이블)

앱(`127.0.0.1:7860`, Gradio)은 **이 컴퓨터에서 도는 로컬 서버**이지 브라우저가 아니다. 그래서 브라우저 캐시를 지워도 데이터는 안 사라진다 — 애초에 브라우저는 아무것도 들고 있지 않고, 서버가 매번 SQLite 파일(`data/kanana_app.sqlite3`)에서 읽어서 화면에 뿌려주는 것뿐이다.

같은 DB 파일 안에 테이블 두 세트가 공존한다 (`fixed/app_store.py`):

- **채팅 로그**: `conversations`(대화 제목/상태), `messages`(user/assistant 메시지) — 이미 구현된 강사 코드, 손댈 필요 없음
- **구조화 데이터**: `structured_requests`(원본 payload 전체 보관, 감사 로그), `schedules`/`todos`/`reminders`(kind별 정규화 테이블) — 이번 주 우리가 채운 부분

## 3. 3주차 메인과제 — 완료한 것

목표: "저장 → 조회 → 새 대화에서도 유지"가 되는 최소 기록장 완성.

| 함수 | 하는 일 |
|---|---|
| `save_structured_request` | 검증된 인자(kind/title/date/...)를 dict로 모아 None 제외 → `AppSQLiteStore.save_structured_request(payload)` 호출 → `structured_requests` + kind에 맞는 정규화 테이블에 동시 저장 |
| `list_saved_requests` | kind/date_from/date_to 필터로 `structured_requests` 원본 목록 조회 |
| `get_saved_request` | request_id로 단건 조회 (없으면 `row=None`) |
| `personal_list_saved_schedules` | kind 기본값을 `personal_schedule`로 잡고 `schedules` 테이블 조회 (이름 자체가 "내 개인 일정" 조회용이라 기본값이 필요) |
| `week03_prompt_parts` / `SQLITE_MEMORY_PROMPT` / `WEEK03_TOOL_CALL_PROMPT` | "구조화 후 저장" 순서, 영속성 안내, 이번 주 tool 선택 규칙을 system prompt에 추가 |
| `build_week03_agent` | `create_agent(model=chat_model(), tools=week03_tools(), system_prompt=week03_system_prompt())`로 agent 조립 |

**추가과제(이번 주 범위 아님, `...` 상태로 남겨둠)**: `personal_update_saved_schedule`, `personal_delete_saved_schedules`, week1-호환 `personal_create_schedule`, `unwrap_legacy_payload`, `_save_input_from`, `save_structured_request_payload`, `structured_request_from_week01_schedule`, `_delete_saved_schedules`, `delete_saved_schedules_dict`.

## 4. `save_structured_request` 함수 안에서 배운 문법/설계

- **`args_schema=SaveStructuredRequestInput`**: LLM이 만든 tool arguments가 함수 본문에 들어가기 *전에* Pydantic이 검증. 함수 안에서 방어적 타입 체크 불필요.
- **dict comprehension으로 None 필터링**:
  ```python
  raw = {"kind": kind, "title": title, ...}
  payload = {key: value for key, value in raw.items() if value is not None}
  ```
- **`_store()`**: `AppSQLiteStore(CONFIG.app_db_path)`를 새로 만드는 헬퍼. "DB 파일에 연결"과 "그 DB에 실제로 쓰는 로직(`fixed/app_store.py`)"은 분리되어 있음.
- **원본(`raw_json`) vs 정규화 테이블을 나누는 이유**: 정규화 테이블은 조회용으로 일부 필드만 뽑은 것이라 정보 손실이 있을 수 있음. 원본을 남겨두면 나중에 재처리/재분류/디버깅이 가능 (감사 로그 역할).
- **`personal_schedule`/`group_schedule`을 같은 `schedules` 테이블에 저장하며 구분하는 법**: 테이블 자체엔 구분 컬럼이 없고, `structured_requests.kind`를 `request_id`로 조인해서 구분 (`SCHEDULE_COLUMNS_WITH_KIND`, `fixed/store_base.py`).
- **`unknown`이 정규화 테이블에 안 들어가는 이유**: kind가 불확실하면 어느 테이블에 넣을지 판단 근거가 없음. 잘못 넣으면 이후 조회/삭제가 오염됨. `structured_requests`에만 남겨서 나중에 재분류 여지를 둠.
- **`personal_list_saved_schedules`가 왜 "회의도 내 일정 아냐?"라는 질문을 남기는가**: 데이터 저장은 personal/group 구분 없이 같은 `schedules` 테이블에 하지만, 조회 기본값을 `personal_schedule`로 좁힌 건 5~6주차에서 개인 일정과 그룹 일정이 외부 공유 저장소 동기화 방식이 달라지기 때문으로 추정됨 (`fixed/app_store.py` 상단 docstring 참고). 이번 주 가이드가 명시적으로 지시한 설계.

## 5. 디버깅 사례 — `personal_create_schedule` 오작동

**증상**: "내일 10시 개인 코칭 저장해줘"라고 하니 `personal_create_schedule` tool이 호출되고 `tool_result.content: null`. 이후 "내 일정 보여줘"도 빈 목록.

**원인**: `week03_tools()`가 Week 1의 `personal_create_schedule`을 이 파일의 동명 함수(Week1 호환, 추가과제라 아직 `...` 미구현)로 바꿔치기해서 노출하고 있었는데, system prompt가 이 tool을 명시적으로 막지 않아서 LLM이 (Week 1부터 누적된 "personal_create_schedule을 써라"는 오래된 지시를 따라) 이 tool을 선택함. 미구현이라 `None` 반환 → 실제 저장 안 됨.

**해결**: `WEEK03_TOOL_CALL_PROMPT`에 "personal_create_schedule은 이번 주(Week 3)에는 사용하지 않는다 — 새 일정 생성 요청은 반드시 extract_schedule_request로 구조화한 뒤 save_structured_request로 저장한다"를 명시적으로 추가. 앱 재시작(`_WEEK03_AGENT` 전역 캐시라 재시작해야 새 프롬프트 반영) 후 재테스트 → 정상 동작 확인.

**교훈**: tool 목록에 이름이 비슷하거나 오래된 tool이 남아있으면, system prompt가 최신 지시를 명시적으로 우선시켜야 함. `join_system_prompt`의 "더 뒤에 있는 지시를 우선한다"는 원칙은 있지만, 실제로는 구체적인 tool 이름을 직접 언급해서 못박아야 확실히 통한다.

## 6. `extract_schedule_request` → `save_structured_request` 흐름 (2단계 tool 호출 + LLM 2번 등장)

```
사용자: "내일 10시 개인 코칭 저장해줘"
   │
   ▼
[메인 agent LLM] (build_week03_agent, week03_system_prompt를 따름)
   │  "저장 요청 → 먼저 extract_schedule_request"
   ▼
extract_schedule_request(query)          ← tool 호출 1 (student_parts/week02_..., L234)
   │  내부에서 extract_structured_request(text) 호출
   │  → chat_model().with_structured_output(StructuredRequest)  ← 별도 LLM 호출!
   │  → "내일"을 오늘 날짜 기준 계산, kind/title/date/start_time 등 추출
   ▼
{"ok": true, "structured_request": {kind, title, date, start_time, ...}}
   │
   ▼
[메인 agent LLM] 이 JSON을 읽고 "이제 save_structured_request 호출"
   ▼
save_structured_request(kind=..., title=..., ...)   ← tool 호출 2 (student_parts/week03_..., L329)
   │  args_schema=SaveStructuredRequestInput 검증
   │  _store().save_structured_request(payload) → fixed/app_store.py 실제 INSERT
   ▼
{"ok": true, "request_id": "req_...", "saved_rows": [...], "shared_sync": {...}}
```

`extract_schedule_request`와 `save_structured_request`를 굳이 tool 2개로 나눈 이유: "자연어→구조화"와 "구조화된 값→저장"의 책임을 분리해두면, 나중 주차에서 각각 독립적으로 재사용 가능 (예: 이미 구조화된 값이 있는 다른 흐름에서 저장만 필요할 때 `save_structured_request`만 재사용).

### Week 1 tool 3개의 운명 (Week 3 시점)

| Week 1 tool | Week 3에서 상태 |
|---|---|
| `personal_create_schedule` | **교체됨.** 같은 이름의 Week 3 호환 버전(추가과제, 미구현)으로 바뀜. system prompt로 "쓰지 마라" 차단. |
| `personal_list_schedules` | 코드상 **그대로 살아있고 호출 가능**. system prompt로 "`personal_list_saved_schedules`를 대신 써라" 유도. |
| `personal_delete_schedule` | 코드상 **그대로 살아있고 호출 가능**. system prompt로 "이번 주는 수정/삭제 안 함" 전반 차단. |

tool을 목록에서 제거하지 않고 prompt로 통제하는 이유: `week01_tools()` 자체를 건드리면 별도로 계속 돌아가야 하는 Week 1/2 agent(`build_week01_agent`, `build_week02_agent`)가 깨지기 때문.

## 7. 완료 기준 검증 결과 (2026-07-15)

- ✅ "내일 10시 개인 코칭 저장해줘" → `extract_schedule_request` → `save_structured_request` 순서로 호출, `structured_requests` + `schedules` 테이블에 저장 확인
- ✅ "내 일정 보여줘" → `personal_list_saved_schedules`가 방금 저장한 일정을 반환
- ✅ 새 대화(새 `conversation_id`)를 열어도 저장된 일정이 그대로 조회됨 → SQLite 영속성 확인 완료

메인과제 통과. 남은 건 추가과제(수정/삭제, 외부 동기화, 레거시 정규화) — 필요시 이어서 진행.
