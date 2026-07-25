# Week 4 심화과제 + 멘토링 요구사항 정리

이 문서는 **구현 전 정리 문서**입니다. 실제 코드는 이 문서로 방향을 합의한 뒤 별도로 작성합니다.

두 가지를 분리해 정리합니다.
- **A. 심화과제 자체가 요구하는 것** (과제 가이드 기준)
- **B. 멘토링이 추가로 요구하는 것** (PR 리뷰 코멘트 기준)

---

## A. 심화과제가 요구하는 것 (과제 가이드 기준)

가이드(`student_parts/week04_retrieve_nanas_memory.py` 74-90번 줄)가 정의한 심화(추가)과제의 핵심 대상은 **`search_conversation_messages` 한 갈래**입니다. "일반 채팅 발화"를 출처로 하는 세 번째 RAG 검색이에요.

### 지금 스텁으로 남아있는 함수 (구현 대상)

| 함수 | 위치 | 역할 | 티어 |
| --- | --- | --- | --- |
| `search_conversation_messages_dict(...)` | `week04_retrieve_nanas_memory.py:265` | lazy sync + 검색 본체, dict 반환 | 심화 |
| `search_conversation_message_rows(...)` | `week04_retrieve_nanas_memory.py:279` | 위 dict에서 hits만 꺼내는 helper | 심화 |
| `search_conversation_messages(...)` (tool) | `week04_retrieve_nanas_memory.py:316` | 위를 감싸 JSON 문자열 반환하는 @tool | 심화 |
| `search_nana_memory(...)` (tool) | `week04_retrieve_nanas_memory.py:328` | 참고자료+일정 통합 검색 (구버전 호환) | 참고용 |

`search_nana_memory`는 가이드 88-90번 줄이 "학생 핵심 구현 대상 4개"에서 빼두고 "이전 버전 호환용"이라 명시했고 `week04_tools()`에도 안 들어가 있습니다 → **심화과제 필수 아님.** 이번 범위에서는 건드리지 않아도 됩니다.

### 가이드가 요구하는 동작 (74-79번 줄)

1. **lazy sync**: SQLite에 저장된 앱 대화 메시지를 `ConversationRAGStore.sync_from_sqlite(...)`로 ChromaDB에 동기화한 뒤 검색한다.
2. **현재 대화 제외**: `conversation_id`를 명시하지 않으면 "지금 진행 중인 대화"는 검색에서 빼서, 방금 한 말이 과거 검색 결과처럼 섞이지 않게 한다.
3. **반환 JSON 계약**: `hits`와 `rows`에 같은 결과를 넣고, `context`/`rag_backend`/`sync`도 함께 담는다.
4. **hit 근거**: 각 hit에 `conversation_id`, `role`, `content` 등 대화 근거가 있어야 하며, assistant(=Nana 자신)의 과거 발화만으로 사실을 확정하지 않는다.

### 사용할 이미 완성된 코드 (fixed/, 수정 금지)

- `ConversationRAGStore.sync_from_sqlite(sqlite_store)` → `{upserted, skipped, deleted, total}` 반환 (변경분만 upsert, `source_hash`로 판별)
- `ConversationRAGStore.search(*, query, top_k, exclude_conversation_id, conversation_id)` → hit 리스트
- `ConversationRAGStore.context_from_hits(hits)` → 사람이 읽기 좋은 문자열
- `ConversationRAGStore.backend_info()` → vector backend 설명 dict
- `current_session_scope()` (`fixed/session_scope.py`) → 현재 대화 ID, 대화 밖이면 `"__direct_tool_call__"`

### ⚠️ 가장 헷갈리는 지점 — `conversation_id` vs `exclude_conversation_id`

`ConversationRAGStore.search()`의 두 파라미터는 **상호배타적**이다 (실제 코드 조건: `if not conversation_id and exclude_conversation_id and hit==exclude: continue`). 즉:
- `conversation_id`가 채워지면 → 그 대화로 **좁혀서** 검색 (exclude 로직은 아예 안 탐)
- `conversation_id`가 없을 때만 → `exclude_conversation_id`가 그 대화를 **결과에서 제외**

가이드 "conversation_id 명시 안 하면 현재 대화 제외"를 코드로 옮기면:
- tool 인자 `conversation_id`가 있으면 → store `conversation_id`로 그대로 전달
- tool 인자 `conversation_id`가 `None`이면 → `current_session_scope()`를 store `exclude_conversation_id`로 전달

이 둘을 서로 바꿔 넣으면 "현재 대화만 검색" / "현재 대화 빼고 검색"이 정반대로 동작한다. **멘토가 B안에서 콕 집어 경고한 지점이 정확히 이것.**

---

## B. 멘토링이 요구하는 것 (PR 리뷰 코멘트 기준)

리뷰어(GitJIHO)가 `week04_tools()` (341-350번 줄)에 남긴 코멘트의 요지.

### B-0. 멘토가 지적한 실제 문제

`search_conversation_messages`는 본문이 아직 TODO 스텁인데, **`week04_tools()` 목록에는 그대로 들어가 있다.** docstring은 정상 동작하는 tool처럼 쓰여 있어서, "저번에 뭐라고 했지?" 같은 질문에서 **LLM이 이 미완성 tool을 골라 호출할 수 있다.** (Week 3의 `personal_create_schedule` swap 회귀와 "같은 결의 문제")

### B-1. 멘토가 짚은 핵심 통찰 — 세 검증이 모두 이걸 못 잡는다

| 검증 도구 | 왜 이 문제를 못 잡나 |
| --- | --- |
| `tool_inventory.py` 회귀 탐지 | "이전 주차엔 되던 게 이번에 스텁이 됐나"만 봄. 이 tool은 week4에 **처음 등장**이라 비교할 이전 상태가 없음 |
| `tool_inventory.py` prompt 언급 검사 | 스텁은 애초에 검사 대상에서 제외(`non_stub_names`만 봄) |
| 500케이스 리포트 | 이 tool은 "범위 밖"이라고 리포트에 직접 명시 |

→ 세 검증 모두 **"구현한 코드가 맞게 동작하는가"**만 보도록 설계됨. **"구현 안 한 코드가 여전히 노출돼 있는가"**는 원래부터 아무도 안 보고 있었다. (멘토: 검증 도구를 다시 손볼 필요는 없다)

### B-2. 멘토가 제시한 두 갈래 선택지

| 선택지 | 내용 | 신경 쓸 점 |
| --- | --- | --- |
| **A안 (최소)** | `week04_tools()`에서 `search_conversation_messages`만 잠깐 뺀다 | 미완성 tool 노출 자체를 제거. 심화과제는 안 함 |
| **B안 (구현)** | `search_conversation_messages`를 마저 구현한다 | 아래 2가지 필수 |

**B안 선택 시 멘토의 2가지 필수 조건:**
1. **`conversation_id` 필터와 "현재 대화 제외" 로직을 혼동하지 말 것** — `current_session_scope()` 기준으로 정확히 구현 (위 A절 ⚠️ 지점과 동일)
2. **구현 후 500케이스 하네스에 최소한의 케이스라도 추가해 실제로 검증할 것** — "스텁이 아니게 됐다고 자동으로 검증되는 건 아니다"

타이밍은 이번 PR이든 2차 PR이든 자유.

---

## C. 이번 작업의 방향 (사용자가 "심화과제 구현" 선택)

사용자가 심화과제 구현을 택했으므로 **B안**으로 진행. 그 경우 이 문서 기준으로 해야 할 일:

1. `search_conversation_messages_dict` 구현 — sync + search(현재 대화 제외 매핑 정확히) + `hits/rows/context/rag_backend/sync` 반환
2. `search_conversation_message_rows` 구현 — 위에서 hits만 반환
3. `search_conversation_messages` (tool) 구현 — 위를 `safe_limit` + `json_payload`로 감싸기
4. (A안은 불필요해짐 — 구현하면 더 이상 스텁이 아니므로 `week04_tools()`에서 뺄 이유 없음)
5. **멘토 필수조건 2**: 심화과제용 검증 케이스 추가 — 최소한 "과거 대화 내용을 묻는 질문 → `search_conversation_messages` 호출" + "현재 대화가 결과에서 제외되는가"를 확인하는 케이스. (500케이스 방법론 재사용)

`search_nana_memory`는 이번 범위 밖(참고용)으로 두는 것을 제안. 확정이 필요하면 구현 착수 전 결정.

### 구현 착수 전 확인이 필요한 것

- **검증 케이스를 어디에 둘지**: 500케이스는 스크래치 스크립트였고 저장소에 없음. 심화 검증 케이스도 임시 스크립트로 돌리고 결과만 `docs/`에 리포트로 남길지, 아니면 이번엔 `checks/`에 재현 가능한 형태로 커밋할지.
- **`search_nana_memory` 포함 여부**: 위 제안(범위 밖)대로 둘지.
