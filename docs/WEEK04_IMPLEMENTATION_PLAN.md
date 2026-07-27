# Week 4 구현 계획 — student_parts/week04_retrieve_nanas_memory.py

이 문서는 실행/구현 전 단계 설계 문서입니다. 실제 코드 수정은 이 문서를 보고 별도로 진행합니다.

## 0. 이 주차가 진짜로 요구하는 것

Week 3까지는 "저장"이 핵심이었다면, Week 4는 "검색(RAG)"이 핵심입니다. 그런데 이 과제가 진짜로 가르치려는 건 RAG 자체가 아니라 **검색 대상을 출처별로 쪼개서 tool을 나누는 설계**예요. 데이터 출처는 3곳입니다.

| 출처 | 저장소 | 이 파일의 인스턴스 |
| --- | --- | --- |
| 개인 참고자료 (사용자가 적어둔 메모) | ChromaDB (`fixed/reference_store.py::PersonalReferenceStore`) | `REFERENCE_STORE` |
| 저장된 일정/할일/알림 (Week 3 구조화 기록) | SQLite (`fixed/app_store.py::AppSQLiteStore`) | `SQLITE_STORE` |
| 일반 채팅 발화 | ChromaDB (`fixed/conversation_rag_store.py::ConversationRAGStore`) | `CONVERSATION_RAG_STORE` |

이미 `fixed/` 쪽 저장소 메서드는 대부분 구현이 끝나 있습니다. 이 파일에서 학생이 할 일은 크게 두 가지뿐입니다: **① 그 메서드를 올바른 인자로 호출하고 ② 결과를 tool 계약이 요구하는 JSON 모양(top-level 키 이름 포함)으로 포장하는 것.** 새로 복잡한 알고리즘을 짜는 과제가 아닙니다.

## 1. 구현 순서 (권장)

의존관계상 이 순서가 자연스럽습니다 — 앞 단계가 뒷 단계보다 단순하고, 뒷 단계 구현/검증에 앞 단계 결과가 필요하지는 않으므로 순서를 꼭 지킬 필요는 없지만, 이 순서로 가면 매 단계 끝날 때마다 앱을 켜서 바로 눈으로 확인할 수 있습니다.

1. `add_personal_reference_dict` → `add_personal_reference` (메인)
2. `search_personal_reference_hits` → `search_personal_references` (메인)
3. `search_saved_request_rows` → `search_saved_requests` (메인)
4. `week04_prompt_parts()`에 Week 4 지시문 추가 (메인 — 함수 구현만큼 중요, 아래 5번 참고)
5. `search_conversation_messages_dict`/`search_conversation_message_rows` → `search_conversation_messages` (추가과제)
6. `search_nana_memory` (선택 — 아래 "6번을 건너뛰어도 되는 이유" 참고)

## 2. 단계별 구현 스케치

### 2-1. `add_personal_reference_dict` / `add_personal_reference`

`PersonalReferenceStore.add_personal_reference(title, content, tags=None)`가 이미 `reference_id`/`title`/`content`/`tags`/`backend` 딕셔너리를 반환합니다([fixed/reference_store.py:138-153](fixed/reference_store.py#L138-L153)). 그대로 호출하고 `tags`만 `None → []` 정규화하면 끝입니다.

```python
def add_personal_reference_dict(reference_store, *, title, content, tags=None):
    return reference_store.add_personal_reference(title, content, tags or [])

@tool(args_schema=AddPersonalReferenceInput)
def add_personal_reference(title, content, tags=None):
    reference = add_personal_reference_dict(REFERENCE_STORE, title=title, content=content, tags=tags)
    return json_payload(
        {
            "ok": True,
            "tool_name": "add_personal_reference",
            "reference_backend": reference["backend"],
            "reference": reference,
        }
    )
```

가이드 문구("reference_backend와 reference가 있는 JSON payload")를 그대로 top-level 키 이름으로 씁니다.

### 2-2. `search_personal_reference_hits` / `search_personal_references`

주의할 점 하나: `PersonalReferenceStore.search_personal_references(query, limit)`가 반환하는 hit은 `{"id","title","content","tags","distance"}` 평평한(flat) 구조입니다([fixed/reference_store.py:155-172](fixed/reference_store.py#L155-L172)). 하지만 가이드가 요구하는 계약은 `id, content, distance, metadata(title/tags)` — 즉 `title`/`tags`가 `metadata` 안에 중첩되어야 합니다. **여기서 재구조화(reshape)가 필요합니다.**

```python
def search_personal_reference_hits(reference_store, *, query, top_k=2):
    raw_hits = reference_store.search_personal_references(query, limit=top_k)
    return [
        {
            "id": hit["id"],
            "content": hit["content"],
            "distance": hit["distance"],
            "metadata": {"title": hit.get("title", ""), "tags": hit.get("tags", "")},
        }
        for hit in raw_hits
    ]

@tool(args_schema=SearchPersonalReferencesInput)
def search_personal_references(query, top_k=2):
    hits = search_personal_reference_hits(REFERENCE_STORE, query=query, top_k=safe_limit(top_k, default=2, maximum=20))
    return json_payload({"ok": True, "tool_name": "search_personal_references", "hits": hits})
```

**설계 판단이 필요한 지점:** `tags`가 store에서 `"preference,meeting"`처럼 콤마로 합쳐진 문자열로 저장되어 있습니다. `metadata.tags`를 그 문자열 그대로 둘지, `.split(",")`로 리스트로 되돌릴지는 선택인데 — `add_personal_reference`가 리스트를 받고 저장하므로, 검색 결과도 리스트로 돌려주는 쪽이 왕복(round-trip) 일관성이 있어 보입니다. 다만 필수 요구사항은 아니므로 편한 쪽으로 정하면 됩니다.

### 2-3. `search_saved_request_rows` / `search_saved_requests`

`AppSQLiteStore.search_saved_requests(query, kind=None, limit=5)`가 이미 구현되어 있습니다([fixed/app_store.py:454-476](fixed/app_store.py#L454-L476)) — `raw_json`/`title`/`reason`에 대한 단순 LIKE 검색이고, 결과 없으면 빈 리스트를 돌려줍니다. 재구조화 없이 그대로 통과시키면 됩니다.

```python
def search_saved_request_rows(sqlite_store, *, query, top_k=3):
    return sqlite_store.search_saved_requests(query, limit=top_k)

@tool(args_schema=SearchSavedRequestsInput)
def search_saved_requests(query, top_k=3):
    rows = search_saved_request_rows(SQLITE_STORE, query=query, top_k=safe_limit(top_k, default=3, maximum=50))
    return json_payload({"ok": True, "tool_name": "search_saved_requests", "rows": rows})
```

### 2-4. `week04_prompt_parts()` — 비어 있는 지시문 채우기

지금 `week04_prompt_parts()`([week04_retrieve_nanas_memory.py:350-356](student_parts/week04_retrieve_nanas_memory.py#L350-L356))는 `# TODO` 주석만 있고 실제 지시문이 하나도 없습니다. 함수 4개를 다 구현해도 이 프롬프트가 비어 있으면 LLM이 애초에 어떤 tool을 언제 써야 하는지 알 방법이 없으므로, 이건 사실상 메인과제에 포함되는 작업으로 봐야 합니다.

포함해야 할 내용(가이드 "출처 구분" 섹션, [week04_retrieve_nanas_memory.py:81-85](student_parts/week04_retrieve_nanas_memory.py#L81-L85)을 프롬프트 문장으로 옮기는 것):
- "취향/선호/메모"류 질문 → `search_personal_references`
- "일정/할일/알림 저장 기록" 관련 질문 → `search_saved_requests` (Week 3의 `personal_list_saved_schedules`와는 다른 검색 경로임을 구분)
- (추가과제까지 한다면) 과거 잡담/대화 내용 관련 질문 → `search_conversation_messages`
- 질문 성격에 따라 두 개 이상의 tool을 같이 써도 된다는 것
- (추가과제 안내와 동일한 안전장치) assistant 자신의 과거 발화만으로 사실을 확정하지 말 것 — 이건 이미 가이드 79번 줄에 명시된 요구사항이라 프롬프트에 반드시 반영

이 파일에 `current_app_date_iso`가 import만 되어 있고 아직 안 쓰이는 것도 확인했습니다([week04_retrieve_nanas_memory.py:13](student_parts/week04_retrieve_nanas_memory.py#L13)) — 이전 주차들처럼 "오늘 날짜는 {today}이다" 문장을 넣고 싶다면 여기서 쓰면 되고, 굳이 안 써도 무방합니다(단, 안 쓸 거면 import를 남겨둘지 지울지는 취향 문제).

### 2-5. (추가과제) `search_conversation_messages_dict` / `search_conversation_message_rows` / `search_conversation_messages`

여기가 가장 손이 많이 가는 부분입니다. `ConversationRAGStore.search(...)`의 시그니처를 보면 파라미터가 두 개로 나뉘어 있습니다([fixed/conversation_rag_store.py:96-159](fixed/conversation_rag_store.py#L96-L159)):
- `conversation_id` — **이 값이 주어지면 그 대화로만 좁혀서 검색**(명시적 필터)
- `exclude_conversation_id` — **`conversation_id`가 안 주어졌을 때만** 이 대화를 검색 결과에서 뺌(제외 필터). 코드상 `if not conversation_id and exclude_conversation_id and ...` 조건이라 둘이 동시에 의미를 가지지 않습니다.

가이드 문구 "conversation_id를 명시하지 않으면 현재 대화 범위는 검색에서 제외"를 그대로 매핑하면:
- tool의 `conversation_id` 인자(LLM/사용자가 명시적으로 준 값) → store의 `conversation_id`(필터)로 그대로 전달
- tool의 `conversation_id`가 `None`일 때만 → `current_session_scope()`(현재 진행 중인 대화 ID)를 store의 `exclude_conversation_id`로 전달

```python
def search_conversation_messages_dict(sqlite_store, conversation_rag_store, *, query, top_k=5, conversation_id=None):
    sync_result = conversation_rag_store.sync_from_sqlite(sqlite_store)
    hits = conversation_rag_store.search(
        query=query,
        top_k=top_k,
        conversation_id=conversation_id,
        exclude_conversation_id=None if conversation_id else current_session_scope(),
    )
    return {
        "hits": hits,
        "rows": hits,
        "context": conversation_rag_store.context_from_hits(hits),
        "rag_backend": conversation_rag_store.backend_info(),
        "sync": sync_result,
    }

def search_conversation_message_rows(sqlite_store, *, query, top_k=5, conversation_id=None):
    return search_conversation_messages_dict(
        sqlite_store, CONVERSATION_RAG_STORE, query=query, top_k=top_k, conversation_id=conversation_id
    )["hits"]

@tool(args_schema=SearchConversationMessagesInput)
def search_conversation_messages(query, top_k=5, conversation_id=None):
    result = search_conversation_messages_dict(
        SQLITE_STORE, CONVERSATION_RAG_STORE,
        query=query, top_k=safe_limit(top_k, default=5, maximum=50), conversation_id=conversation_id,
    )
    return json_payload({"ok": True, "tool_name": "search_conversation_messages", **result})
```

`current_session_scope()`가 대화 밖(직접 함수 호출 등)에서는 `"__direct_tool_call__"`(`DEFAULT_SESSION_SCOPE`)을 돌려주는데, 그 값은 실제 대화 ID로 저장될 일이 없으므로 exclude 필터로 넣어도 안전합니다(아무것도 안 걸러짐).

`search_conversation_message_rows`는 가이드상 `search_conversation_messages_dict(...)`에서 hits만 꺼내는 내부 helper인데, 매번 `sync_from_sqlite`를 다시 부르는 게 걸리면 — 이 함수가 실제로 앱 안에서 tool 밖에서 재사용되는 곳이 없다면 위 구현으로 충분합니다(중복 sync가 성능 문제가 될 정도의 스케일은 이 수업 범위에서 아님).

### 2-6. `search_nana_memory` — 굳이 지금 안 건드려도 되는 이유

가이드 87-91번 줄이 "학생 핵심 구현 대상은 add_personal_reference, search_personal_references, search_saved_requests, search_conversation_messages 4개"라고 명시하고, `search_nana_memory`는 "참고 코드"/"이전 버전 호환용"이라고 분리해뒀습니다. `week04_tools()`([week04_retrieve_nanas_memory.py:332-341](student_parts/week04_retrieve_nanas_memory.py#L332-L341))에도 이 tool은 포함되어 있지 않습니다 — 즉 지금 agent가 실제로 노출하는 tool 목록에 들어가지 않으므로, 구현하지 않아도 메인/추가과제 검증에는 영향이 없습니다. 시간이 남으면 위 3-4번 helper를 조합해 채워 넣는 정도로 충분합니다.

## 3. 검증 체크리스트 (가이드 93-96번 줄 기준)

- [ ] `./run.sh --week4`로 앱 실행
- [ ] 참고자료 하나를 채팅으로 추가 → trace에서 `add_personal_reference` 호출, `reference_backend`/`reference` 키 확인
- [ ] 방금 추가한 참고자료와 관련된 질문 → trace에서 `search_personal_references` 호출, 결과 JSON의 top-level 키가 정확히 `hits`인지 확인
- [ ] 저장된 일정/할일 관련 질문 → trace에서 `search_saved_requests` 호출, top-level 키가 정확히 `rows`인지 확인
- [ ] (추가과제) 이전에 나눴던 일반 잡담 관련 질문 → `search_conversation_messages` 호출, 방금 만든 현재 대화 내용은 결과에서 빠지는지 확인
- [ ] (추가과제) 같은 질문을 `conversation_id`를 명시해서 다시 물었을 때 그 대화로만 좁혀지는지 확인

## 4. 흔한 실수 포인트 (미리 체크)

- top-level 키 이름 오타/누락 — `hits`/`rows`는 LLM이 프롬프트에서 보고 참조하는 실제 계약이라, 이름이 틀리면 tool은 성공해도 LLM이 결과를 못 알아봄
- `search_personal_reference_hits`에서 store의 flat 구조를 그대로 반환하면(재구조화 누락) `metadata` 키 자체가 없어서 가이드 계약 위반
- `search_conversation_messages`에서 `conversation_id`와 `exclude_conversation_id`를 동시에 채워 넘기는 실수 — store 쪽 조건문이 `conversation_id`가 있으면 exclude 로직을 아예 안 타므로 의도한 대로 안 나올 수 있음
- `week04_prompt_parts()`를 안 채우고 함수만 구현 — trace에서 tool 자체는 잘 동작해도 LLM이 애초에 그 tool을 고르지 않는 상황이 생길 수 있음(3주차 리뷰에서 나온 "서술문 vs 지시문" 이슈와 같은 종류)
