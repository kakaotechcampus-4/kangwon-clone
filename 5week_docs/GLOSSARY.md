# 단어장 — Week 5 (MCP / 외부 데이터) 용어 설명

Week 5 과제(`student_parts/week05_load_kanas_past_conversations.py`)와 설계 문서에 나오는 전문 용어를 처음 보는 사람 기준으로 풀어 쓴 문서입니다. (docs/GLOSSARY.md와 같은 구성 — Week 4에서 이미 다룬 LLM/agent/tool/RAG/ChromaDB 등은 그 문서를 참고하고, 여기서는 Week 5에 새로 나온 것 위주로 정리합니다.)

---

## 0. 이번 과제에서 반드시 이해·구현해야 하는 것 (한눈에)

### 이해해야 하는 개념 3가지

1. **MCP (Model Context Protocol)** — agent가 외부 시스템(여기선 외부 멤버의 대화·일정이 든 SQLite)을 "tool"로 쓰게 해주는 표준 규약. **실제 조회 tool은 이미 `mcp_server/sqlite_mcp_server.py`에 완성돼 있고, 학생은 이 서버를 절대 수정하지 않는다.**

2. **MCP Wrapper (이번 주 학생이 만드는 것)** — 그 MCP 서버 tool을 LangChain agent가 부를 수 있게 한 겹 감싼 `@tool` 함수. 하는 일은 딱 두 가지: **① 인자를 MCP tool에 넘겨 호출 → ② 결과를 그대로(또는 json_payload로 감싸) 반환.** 직접 SQL을 짜거나 데이터를 가공하지 않는다(= 책임 경계). 그래서 "얇은 중개자"다.

3. **MCP 호출의 두 갈래 (⚠ 이번 과제 최대 함정)** — 반환 타입이 다르다:
   - `call_mcp_tool_sync(name, args)` → **문자열(str)** 반환 → **그대로 return**
   - `call_external_tool_payload(name, args)` → **dict** 반환 → **json_payload로 감싸서 return**
   - str을 또 json_payload로 감싸면 이중 인코딩되고, dict를 그대로 return하면 타입이 안 맞는다. 어떤 tool이 어느 쪽인지 아래 표에 명시.

### 구현해야 하는 것 (총 8곳: helper 2 + tool 5 + prompt 1, 추가과제 2)

| 구분 | 이름 | 무엇을 하나 | 호출/반환 |
| --- | --- | --- | --- |
| 메인·tool | `search_previous_conversations` | 외부 멤버 과거 대화 검색 | `call_mcp_tool_sync` → str 그대로 |
| 메인·tool | `load_conversation_messages` | 특정 외부 대화의 메시지 로드 | `call_external_tool_payload` → dict → **json_payload** (유일 예외, 순서 보존) |
| 메인·tool | `extract_schedules_from_history` | 외부 멤버 대화에서 일정(busy-time) 추출 | `call_mcp_tool_sync` → str 그대로 |
| 메인·tool | `list_shared_schedules` | 공유 일정 저장소 row 조회 (Week6 재사용) | `call_mcp_tool_sync` → str 그대로 |
| 메인·tool | `collect_member_schedules` | **내 일정 + 외부 멤버 일정을 같은 구조로 합침** (유일한 로직 tool) | 아래 helper 2개 사용 → `{rows, schedule_summary}` json_payload |
| 메인·helper | `_personal_schedules_for_current_scope()` | 내 일정 모으기: SQLite 저장분 + 현재 대화 임시분(중복 제거) | 직접 읽기 |
| 메인·helper | `_collect_member_schedules(...)` | 내 일정 rows("나") + 외부 rows 합치고 요약 생성 | 내부에서 `extract_schedules_from_history` MCP 호출 |
| 메인·prompt | `week05_prompt_parts()` | 개인=이전 주차 tool / 외부 멤버=MCP wrapper 라고 agent에 안내 | 지시문 작성 |
| 추가·tool | `create_shared_schedule` / `delete_shared_schedule` | 공유 저장소 row 등록/삭제 | `call_mcp_tool_sync` → str 그대로 (안 하면 `week05_tools()`에서 제거) |

### 한 줄 요약
Week 5는 **"외부 데이터를 직접 다루는 게 아니라, 이미 완성된 MCP tool을 얇게 감싸 agent에 연결하는" 주차**다. 5개 tool 중 4개는 `call_mcp_tool_sync` 문자열을 그대로 넘기는 pass-through이고, `load_conversation_messages`만 dict→json_payload, `collect_member_schedules`만 "내 것 + 남의 것 합치기" 로직을 갖는다.

---

## 1. MCP 관련 (이번 주 핵심)

**MCP (Model Context Protocol)**
LLM/agent가 외부 시스템(DB, API, 파일 등)의 기능을 "tool"로 가져다 쓸 수 있게 해주는 표준 규약. 이 프로젝트에서는 외부 멤버의 대화·일정이 담긴 SQLite를 MCP 서버로 감싸서, agent가 SQL을 몰라도 tool 호출만으로 그 데이터를 쓸 수 있게 합니다.

**MCP 서버**
tool들을 실제로 구현해 제공하는 프로그램. 여기서는 `mcp_server/sqlite_mcp_server.py`가 그 서버이고, `search_previous_conversations`·`extract_schedules_from_history` 같은 실제 조회 tool을 갖고 있습니다. **학생은 이 서버를 수정하지 않습니다.**

**MCP wrapper (이번 주 학생이 만드는 것)**
MCP 서버의 tool을 LangChain agent가 부를 수 있는 `@tool` 함수로 한 겹 더 감싼 것. 학생 과제는 "실제 조회"가 아니라 이 "감싸기"입니다 — 인자를 MCP tool에 넘기고, 결과를 agent용 JSON으로 돌려주는 얇은 중개자.

**stdio subprocess (표준입출력 하위 프로세스)**
MCP 서버를 별도 프로그램으로 띄우고 표준입력/표준출력(stdin/stdout)으로 통신하는 방식. `fixed/mcp_client.py`는 tool을 호출할 때마다 `sqlite_mcp_server.py`를 subprocess로 새로 띄웁니다. 매 호출이 프로세스를 새로 만들어서 약간 느리지만, 앱과 외부 시스템을 깔끔히 분리하는 장점이 있습니다.

**`call_mcp_tool_sync(name, args)`**
MCP tool 하나를 동기(순차)로 호출하고 **결과를 문자열로** 돌려주는 헬퍼(이 파일에서 `call_local_mcp_tool_sync`의 별칭). Week 5 조회 wrapper 대부분이 이걸 씁니다.

**`call_external_tool_payload(name, args)`**
위 함수를 호출한 뒤 결과 문자열을 `json.loads`로 파싱해 **dict로** 돌려주는 헬퍼. `load_conversation_messages` 하나만 이걸 씁니다(그래서 결과를 다시 `json_payload`로 감싸야 함).

**동기(sync) vs 비동기(async)**
MCP 호출은 원래 비동기(`async`/`await`)인데, `fixed/mcp_client.py`가 `_run_coroutine_sync`로 감싸서 일반 동기 함수에서도 쓸 수 있게 해줍니다. 학생은 `_sync`가 붙은 버전만 쓰면 되고 async를 직접 다룰 필요는 없습니다.

---

## 2. 데이터 출처 / 저장소

**외부 저장소 (`ExternalPeopleSQLiteStore`)**
외부 멤버(철수·영희·민준·서연·지훈·하린)의 과거 대화와 일정이 담긴 별도 SQLite 파일(`data/kanana_external_people.sqlite3`). 앱 내부 DB와 분리돼 있고, 실제 카카오톡/캘린더 대신 수업용 fixture로 씁니다.

**공유 일정 저장소 (external_schedules 테이블)**
"누가 언제 바쁜지"를 여러 사람이 공유하는 저장소. 앱에서 개인/그룹 일정을 저장하면 여기에도 자동 복사(동기화)됩니다. `list_shared_schedules`로 조회하고, 추가과제 `create/delete_shared_schedule`로 직접 등록/삭제합니다.

**busy-time (바쁜 시간)**
"이 사람은 이 시간에 일정이 있어 바쁘다"는 정보. Week 5는 각 멤버의 busy-time을 모으는 것까지, Week 6은 그걸로 "모두가 비는 공통 시간"을 계산하는 것까지 다룹니다.

**seed 데이터 (fixture)**
저장소를 처음 만들 때 미리 채워 넣는 예제 데이터. `external_people_store.py`의 `JULY_PRACTICE_*`가 7월 7~17일 6명의 일정을 미리 심어둡니다. 그래서 구현 후 바로 "철수 7월 일정"을 조회하면 결과가 나옵니다.

---

## 3. 이번 주 함수/개념

**wrapper tool (래퍼 도구)**
실제 일을 하는 다른 함수/서버를 얇게 감싸서, 호출 형식만 맞춰 넘기고 결과만 돌려주는 tool. Week 5 tool 대부분이 "MCP 호출 한 줄 + return"인 이유입니다. 직접 SQL이나 정규화 로직을 넣지 않는 게 "책임 경계"입니다.

**책임 경계 (separation of concerns)**
"어디까지가 누구 일인가"의 선. Week 5에서는 실제 SQL/정규화는 MCP 서버·store의 책임이고, wrapper의 책임은 "호출과 전달"뿐입니다. wrapper에서 멤버 이름을 또 정규화하면 이 경계를 침범하는 것(중복 처리).

**정규화 (normalize)**
입력값을 일관된 표준 형태로 다듬는 것. 예: 멤버 이름 앞뒤 공백 제거·별칭 치환(`normalize_external_member_names`), 날짜에서 시간 부분 잘라내기(`normalize_external_schedule_date_bounds`). 이 프로젝트에선 MCP 경계에서 한 번만 하도록 설계돼 있습니다.

**`collect_member_schedules` (이번 주 핵심 tool)**
"내 일정(앱 내부) + 외부 멤버 일정(MCP)"을 **같은 row 구조로 합쳐** 한 번에 돌려주는 tool. 서로 다른 두 출처를 하나의 표로 통일하는 게 포인트이고, Week 6의 "공통 가능 시간 찾기"가 이 결과를 근거로 씁니다.

**scope (대화 범위)**
지금 실행이 어느 대화(conversation)에 속하는지. `PERSONAL_SCHEDULES`(임시 일정)에는 여러 대화의 일정이 섞여 있을 수 있어, `collect_member_schedules`는 **현재 대화 범위**의 것만 추려야 합니다(`current_session_scope()` 기준). Week 4 GLOSSARY의 session_scope 항목과 같은 개념.

**pass-through (그대로 전달)**
받은 결과를 가공하지 않고 그대로 반환하는 것. Week 5 조회 wrapper 4개가 전부 pass-through입니다(MCP 결과 문자열을 손대지 않고 return).

---

## 4. Week 6와의 관계 (미리 알아두면 좋은 것)

- Week 5: 외부 멤버 busy-time **조회·수집**까지 (`collect_member_schedules`, `list_shared_schedules`)
- Week 6: 모은 busy-time으로 **여러 사람의 공통 가능 시간 선택**까지 (`find_common_available_slots` 등)
- 그래서 Week 5의 `collect_member_schedules`와 `list_shared_schedules`가 "Week 6 Kana 하위 agent가 그대로 재사용하는 연결 지점"이라 메인과제로 지정된 것입니다.
