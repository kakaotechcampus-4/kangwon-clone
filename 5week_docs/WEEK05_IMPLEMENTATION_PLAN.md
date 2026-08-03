# Week 5 구현 계획 — student_parts/week05_load_kanas_past_conversations.py

이 문서는 실행/구현 전 단계 설계 문서입니다. 실제 코드 수정은 이 문서를 보고 별도로 진행합니다.
(docs/WEEK04_IMPLEMENTATION_PLAN.md와 같은 구성)

## 0. 이 주차가 진짜로 요구하는 것

Week 4까지는 "앱 내부(내 것)" 데이터를 다뤘다면, Week 5는 **"외부(남의 것) 데이터를 MCP로 감싸는" 주차**입니다. 핵심은 **학생이 직접 SQL을 짜지 않는다**는 것 — 실제 조회 로직은 이미 외부 SQLite store와 MCP 서버에 다 있고, 학생은 그 **MCP tool을 호출하고 결과를 agent용 JSON으로 전달하는 wrapper tool**만 만듭니다.

데이터 출처가 이제 "내 것"과 "남의 것"으로 갈립니다.

| 출처 | 실제 저장/조회 코드 (이미 완성, 수정 금지) | 접근 방법 |
| --- | --- | --- |
| 외부 멤버의 과거 대화·일정 | `fixed/external_people_store.py::ExternalPeopleSQLiteStore` + `mcp_server/sqlite_mcp_server.py` | MCP tool 호출 |
| 공유 일정 저장소(external_schedules) | 위와 같은 store (앱이 개인/그룹 일정 저장 시 자동 동기화되는 곳) | MCP tool 호출 |
| 내 일정 | `fixed/app_store.py::AppSQLiteStore.list_schedules` + `week01`의 `PERSONAL_SCHEDULES` | 직접 읽기(파이썬) |

이 파일에서 학생이 할 일은 두 가지뿐입니다: **① MCP tool을 올바른 인자로 호출하고 ② 결과를 그대로(또는 json_payload로 감싸) 반환하는 것.** 단, `collect_member_schedules`만 예외적으로 "내 것 + 남의 것"을 **합치는** 로직이 들어갑니다.

## 1. MCP 호출의 두 갈래 (가장 먼저 이해할 것)

이 파일 상단에서 별칭이 정의돼 있습니다.
```python
call_mcp_tool_sync = call_local_mcp_tool_sync   # → str 반환
```
그리고 import된 `call_external_tool_payload`는 다릅니다.

| 함수 | 반환 타입 | 내부 동작 | 이 파일에서 쓰는 tool |
| --- | --- | --- | --- |
| `call_mcp_tool_sync(name, args)` | **문자열(str)** | MCP subprocess 호출 후 텍스트 정규화 | search_previous / extract_schedules / list_shared / create / delete |
| `call_external_tool_payload(name, args)` | **dict** | 위를 호출한 뒤 `json.loads`로 파싱 | load_conversation_messages |

**핵심 함정**: 대부분 tool은 `call_mcp_tool_sync`(문자열)를 써서 **그 문자열을 그대로 return**하면 되지만, `load_conversation_messages`만 `call_external_tool_payload`(dict)를 써서 **json_payload로 다시 감싸** 반환해야 합니다. 반환 타입을 혼동하면 이중 인코딩되거나 문자열을 dict처럼 다루다 깨집니다.

> 참고: MCP 서버(`mcp_server/sqlite_mcp_server.py`)는 `call_local_mcp_tool`이 호출될 때마다 stdio subprocess로 떠서 tool을 실행합니다(`fixed/mcp_client.py`). 매 호출이 프로세스를 새로 띄우므로 느릴 수 있지만, 이 수업 규모에선 문제되지 않습니다.

## 2. 구현 순서 (권장)

1. `search_previous_conversations` (메인, 가장 단순 — 문자열 pass-through)
2. `load_conversation_messages` (메인, 유일하게 payload→json_payload)
3. `extract_schedules_from_history` (메인, 문자열 pass-through)
4. `list_shared_schedules` (메인, 문자열 pass-through)
5. `_personal_schedules_for_current_scope` → `_collect_member_schedules` → `collect_member_schedules` (메인, 유일한 "합치기" 로직)
6. `week05_prompt_parts()` 지시문 추가 (메인 — Week 4 교훈상 함수만큼 중요)
7. `create_shared_schedule` / `delete_shared_schedule` (추가과제)

## 3. 단계별 구현 스케치

### 3-1. `search_previous_conversations` (메인)

가이드: query/member_names/limit를 넘기고 결과 문자열을 그대로 반환. **멤버 이름 정규화는 MCP 경계에서 한 번만 하므로 wrapper에서 중복 변환하지 않는다.**

```python
@tool(args_schema=SearchPreviousConversationsInput)
def search_previous_conversations(query, member_names=None, limit=5):
    args = {"query": query, "member_names": member_names, "limit": limit}
    return call_mcp_tool_sync("search_previous_conversations", args)
```

### 3-2. `load_conversation_messages` (메인 — 유일한 예외)

가이드: `call_external_tool_payload`로 dict를 받아 json_payload로 감싼다. **sender/content/created_at 순서 보존 — 결과를 가공하지 않는다.**

```python
@tool(args_schema=LoadConversationMessagesInput)
def load_conversation_messages(conversation_id):
    payload = call_external_tool_payload("load_conversation_messages", {"conversation_id": conversation_id})
    return json_payload(payload)
```

### 3-3. `extract_schedules_from_history` (메인)

가이드: rows가 member_name/title/date/start_time/end_time/notes를 유지. 날짜 정리도 MCP 경계에서 처리하므로 wrapper에선 안 함.

```python
@tool(args_schema=ExtractSchedulesFromHistoryInput)
def extract_schedules_from_history(member_names, date_from, date_to):
    args = {"member_names": member_names, "date_from": date_from, "date_to": date_to}
    return call_mcp_tool_sync("extract_schedules_from_history", args)
```

### 3-4. `list_shared_schedules` (메인)

가이드: 공유 저장소 row 조회. 필터 없이 호출하면 기본 실습 공유 일정이 반환됨(store의 `has_explicit_filter` 로직). Week 6 Kana 하위 agent가 그대로 재사용.

```python
@tool(args_schema=ListSharedSchedulesInput)
def list_shared_schedules(member_names=None, date_from=None, date_to=None, source_conversation_id=None, limit=50):
    args = {
        "member_names": member_names, "date_from": date_from, "date_to": date_to,
        "source_conversation_id": source_conversation_id, "limit": limit,
    }
    return call_mcp_tool_sync("list_shared_schedules", args)
```

### 3-5. `collect_member_schedules` 계열 (메인 — 유일한 합치기 로직, 가장 손이 감)

이 tool만 "내 것 + 남의 것"을 같은 row 구조로 합칩니다. Week 6의 공통 가능 시간 tool이 이 rows를 busy_rows 근거로 씁니다.

**(a) `_personal_schedules_for_current_scope()`** — 내 일정 모으기
- SQLite 저장 일정: `AppSQLiteStore(CONFIG.app_db_path).list_schedules(...)` (Week 3+ 저장분)
- 임시 일정: `PERSONAL_SCHEDULES` 중 `_schedule_scope(s) == current_session_scope()`인 것만
- **중복 제거**: SQLite에 이미 있는 일정과 임시 일정이 겹치지 않도록 schedule_id/id 기준으로 한 번 걸러냄

**(b) `_collect_member_schedules(...)`** — 실제 합치기
- 내 일정 rows → member_name="나"로, `_structured_request_from_schedule_row`로 필드 정리
- 외부 멤버 rows → 이 함수 안에서 `call_mcp_tool_sync("extract_schedules_from_history", args)` 호출 후 `json.loads`로 rows 파싱
- 멤버 이름/날짜는 `normalize_external_member_names`, `normalize_external_schedule_date_bounds`로 정규화
- 두 출처를 member_name/title/date/start_time/end_time/notes rows로 합침
- `external_schedule_summary(rows)`로 `schedule_summary` 생성

**(c) `collect_member_schedules(...)` tool** — 위를 감싸 반환
```python
@tool(args_schema=CollectMemberSchedulesInput)
def collect_member_schedules(member_names, date_from, date_to):
    result = _collect_member_schedules(
        member_names=member_names, date_from=date_from, date_to=date_to,
        personal_schedules=_personal_schedules_for_current_scope(),
    )
    return json_payload(result)
```
반환 dict에는 `rows`(합쳐진 일정)와 `schedule_summary`가 있어야 합니다.

### 3-6. `week05_prompt_parts()` — 비어 있는 지시문 채우기

지금 `# TODO`만 있음. Week 4에서 뼈저리게 확인했듯 함수를 다 구현해도 프롬프트에 tool 사용 지침이 없으면 LLM이 안 고릅니다. 넣을 내용:
- 개인 저장/RAG(내 일정·참고자료·과거 대화)는 이전 주차 tool로 처리
- **외부 멤버**의 과거 대화 검색/로드/일정 추출은 Week 5 MCP wrapper(`search_previous_conversations`/`load_conversation_messages`/`extract_schedules_from_history`)로
- 여러 사람 일정을 한 번에 모을 땐 `collect_member_schedules`, 공유 저장소 확인은 `list_shared_schedules`
- "여러 사람의 최종 회의 시간 선택"은 Week 6 범위이므로 Week 5에선 조회/수집까지만

### 3-7. (추가과제) `create_shared_schedule` / `delete_shared_schedule`

각각 `call_mcp_tool_sync("create_shared_schedule"/"delete_shared_schedule", args)` 호출 후 결과 그대로 반환. `schedule_id` 또는 `source_conversation_id`를 보존해야 이후 수정/삭제 동기화가 가능. **구현 안 하려면 `week05_tools()` 목록에서 두 tool을 빼면 됨** (Week 4의 stub 노출 문제를 반복하지 않으려면 이 편이 안전).

## 4. 검증 체크리스트 (가이드 113-120번 줄 기준)

- [ ] `./run.sh --week5`로 앱 실행
- [ ] "철수랑 영희 7월 일정 알려줘" 같은 외부 팀원 일정 조회 → trace에서 search_previous_conversations / load_conversation_messages / extract_schedules_from_history 호출 순서 확인
- [ ] `collect_member_schedules` 결과 rows에 "나"와 외부 멤버 일정이 **같은 구조**(member_name/title/date/start_time/end_time/notes)로 들어있는지
- [ ] `list_shared_schedules` 결과에 rows와 schedule_summary가 유지되는지
- [ ] (추가) create_shared_schedule로 등록한 row가 list_shared_schedules에 나타나고 delete_shared_schedule로 사라지는지

## 5. 흔한 실수 포인트 (미리 체크)

- **반환 타입 혼동**: `load_conversation_messages`만 `call_external_tool_payload`(dict)→json_payload, 나머지는 `call_mcp_tool_sync`(str)→그대로 return. 섞으면 이중 인코딩/타입 에러.
- **중복 정규화**: 멤버 이름/날짜는 MCP 경계(store)에서 이미 정규화됨 — wrapper에서 또 하면 책임 경계 위반이고 이중 처리.
- **collect_member_schedules의 임시 일정 처리**: `PERSONAL_SCHEDULES` 전체를 합치면 (1) 다른 대화 범위의 임시 일정, (2) 이미 SQLite에 저장된 일정이 중복됨 → 반드시 현재 scope 필터 + id 기준 중복 제거.
- **메시지 순서 가공**: `load_conversation_messages`는 sender/content/created_at 순서를 그대로 보존해야 함(정렬/필터 금지).
- **week05_prompt_parts() 미작성**: 함수는 되는데 LLM이 tool을 안 고르는 Week 4와 동일한 함정.
- **추가과제 stub 노출**: create/delete를 구현 안 할 거면 `week05_tools()`에서 빼기 — 안 그러면 Week 4에서 멘토가 지적한 "미완성 stub이 목록에 노출" 문제 재발.
