# 단어장 — `docs/SUMMARY.md` 용어 설명

`docs/SUMMARY.md`에 나오는 전문 용어/줄임말을 처음 보는 사람 기준으로 풀어 쓴 문서입니다. 카테고리별로 묶었고, 같은 용어가 여러 곳에 나와도 한 번만 설명합니다.

---

## 1. AI / LLM 기본 개념

**LLM (Large Language Model)**
대화하고 글을 만들어내는 거대 언어모델. 이 프로젝트에서 "Nana"라는 챗봇을 움직이는 두뇌 역할이에요.

**agent (에이전트)**
그냥 LLM이 아니라, "필요하면 도구(tool)를 스스로 선택해서 호출할 수 있는" LLM을 말해요. `create_agent(...)`로 만든 결과물이 agent입니다.

**tool (도구)**
agent가 호출할 수 있는 파이썬 함수. `@tool`이라는 표시가 붙어 있어야 agent가 그 함수의 존재를 알고 호출할 수 있어요. 예: `search_personal_references`, `search_saved_requests`.

**prompt / system prompt**
LLM에게 미리 주는 "너는 이런 역할이고 이렇게 행동해라"라는 지시 글. `week04_prompt_parts()`가 만드는 문자열들이 이거예요.

**지시문 vs 서술문**
"지시문"은 "~할 때 이 tool을 써라"처럼 행동을 직접 명령하는 문장. "서술문"은 "이번 주는 저장까지만 다룬다"처럼 상황을 설명만 하는 문장. LLM은 지시문은 잘 따르지만, 서술문만 있으면 "그래서 뭘 하지 말라는 거지?"를 스스로 추론해야 해서 안 지킬 수 있어요. SUMMARY.md에서 이 둘을 구분하는 이유가 이거예요.

**RAG (Retrieval-Augmented Generation)**
"검색 후 생성"이라는 뜻. LLM이 자기 기억만으로 답하지 않고, 먼저 관련 자료를 검색해서 찾은 다음 그 내용을 참고해서 답을 만드는 방식이에요. Week 4가 이걸 다룹니다.

**embedding (임베딩)**
글자(문장)를 숫자 벡터로 바꾸는 작업. "의미가 비슷한 문장은 벡터도 서로 가깝다"는 성질을 이용해서 "정확히 같은 단어"가 아니라 "의미가 비슷한 내용"을 검색할 수 있게 해줘요. RAG 검색의 핵심 기술입니다.

**trace**
한 번의 채팅에서 "어떤 tool이 호출됐고, 어떤 값이 오갔는지"를 그대로 기록한 JSON. 앱 화면의 "상세" 탭에서 보여주는 그 데이터예요.

---

## 2. 저장소 / 데이터베이스

**SQLite**
파일 하나가 통째로 데이터베이스인 가벼운 DB. 이 프로젝트에서는 `data/kanana_app.sqlite3` 파일이 그 DB예요.

**ChromaDB / vector store**
"의미 기반 검색"을 위한 데이터베이스(벡터 DB). embedding으로 바꾼 벡터들을 저장해두고, 새 질문이 들어오면 그 질문의 벡터와 가장 가까운 것들을 찾아줘요. `PersonalReferenceStore`, `ConversationRAGStore`가 내부적으로 ChromaDB를 씁니다.

**metadata**
검색 결과(hit)에 딸려오는 "부가 정보". 예: 참고자료 검색 결과의 `metadata.title`, `metadata.tags`처럼, 실제 본문(`content`)과는 별개로 붙는 제목/태그 같은 정보예요.

**backend**
"이 데이터가 실제로 어떤 시스템/설정으로 처리됐는지"를 설명하는 정보. `backend_info()`가 돌려주는 `{"vector_store": "chromadb", "embedding_model": ...}` 같은 dict예요. 사용자에게 "이 결과가 어디서 나온 건지" 투명하게 보여주는 용도입니다.

**sync (동기화), lazy sync**
두 저장소의 내용을 같게 맞추는 작업. "lazy sync"는 "미리미리 동기화해두는 게 아니라, 검색이 필요한 바로 그 순간에 동기화한다"는 뜻이에요. `ConversationRAGStore.sync_from_sqlite(...)`가 검색 직전에 SQLite 대화 내용을 ChromaDB로 동기화하는 게 이 방식입니다.

**flat 구조 vs 중첩(nested) 구조**
flat 구조는 `{"id": .., "title": .., "tags": ..}`처럼 모든 값이 한 층에 나란히 있는 것. 중첩 구조는 `{"id": .., "metadata": {"title": .., "tags": ..}}`처럼 값 일부가 다시 그 안에 딕셔너리로 들어있는 것. `search_personal_reference_hits`에서 store가 주는 flat 결과를 가이드가 원하는 중첩 구조로 바꿔야 했던 게 이 개념이에요.

---

## 3. 코드/설계 용어

**stub (스텁)**
아직 구현 안 하고 자리만 잡아둔 빈 함수. 이 프로젝트에서는 함수 본문에 `...`(Ellipsis, 파이썬에서 "아무것도 안 함"을 나타내는 특수 값)만 있는 상태를 말해요.

**회귀 (regression)**
예전엔 잘 되던 기능이 이후 변경으로 다시 고장 나는 것. Week 3에서 "1주차 때 잘 되던 `personal_create_schedule`이 3주차 조립 코드 때문에 스텁으로 바뀌어버린" 사건이 정확히 이 회귀 사례예요.

**reshape (재구조화)**
데이터의 "모양"(키 구조)을 다른 모양으로 바꾸는 것. 위 "flat vs 중첩" 항목이 바로 reshape가 필요했던 예시입니다.

**round-trip (라운드트립)**
"데이터를 저장했다가 다시 꺼냈을 때, 원래 넣었던 것과 같은 형태로 돌아오는지"를 나타내는 개념. `tags`를 리스트로 넣었으면 검색해서 꺼낼 때도 리스트로 돌아와야 round-trip이 일관된다고 표현해요.

**pass-through (패스스루)**
받은 데이터를 가공하지 않고 그대로 통과시켜 반환하는 것. `search_saved_request_rows`는 store가 준 결과를 손대지 않고 그대로 돌려주므로 pass-through입니다.

**dead code (죽은 코드) / 방어 코드**
실행은 되지만 "정상적인 경로에서는 절대 발동하지 않는" 코드. 예: 이미 Pydantic이 걸러준 값에 대해 또 `if x is None` 체크를 하는 경우. 나쁜 건 아니지만 불필요한 경우가 많아서, 있다는 걸 인지하고 넘어가는 게 중요해요.

**전역 변수 (global)**
함수 안이 아니라 파일 최상단에 선언돼서, 그 파일의 어떤 함수에서도 꺼내 쓸 수 있는 변수. `REFERENCE_STORE`, `SQLITE_STORE`, `_WEEK04_AGENT` 같은 것들이 전역 변수예요.

**monkeypatch (몽키패치)**
원래 코드를 고치지 않고, 실행 중에 "이 함수/객체를 잠깐 다른 걸로 바꿔치기"해서 테스트하는 기법. `ASSIGNMENT_CHECK_DESIGN.md`에서 "쓰기 tool을 격리된 DB로 테스트하려면 monkeypatch가 필요하다"고 한 게 이 뜻이에요 — 전역 `SQLITE_STORE`를 테스트 동안만 가짜(임시) store로 바꿔치기해야 하기 때문입니다.

**상호배타 (mutually exclusive)**
두 가지 중 하나만 의미를 가지고, 동시에 둘 다 적용되지는 않는 관계. `ConversationRAGStore.search()`의 `conversation_id`와 `exclude_conversation_id`가 이 관계였어요 — 하나가 채워지면 다른 하나는 무시됩니다.

**파라미터 (parameter)**
함수를 호출할 때 넘기는 입력값의 자리. 예를 들어 `search(query, top_k, conversation_id)`에서 `query`/`top_k`/`conversation_id` 하나하나가 파라미터입니다.

**조건문 (conditional statement)**
"이 조건이면 이렇게, 아니면 저렇게" 분기하는 코드. 파이썬의 `if ... else ...` 문이 조건문입니다.

---

## 4. 이 프로젝트 특정 변수/클래스 이름

**`PersonalReferenceStore` / `REFERENCE_STORE`**
개인 참고자료(사용자가 적어둔 메모)를 ChromaDB에 저장/검색하는 클래스와, 그 클래스로 만들어둔 실제 인스턴스(전역 변수)예요.

**`AppSQLiteStore` / `SQLITE_STORE`**
일정/할일/알림 등 구조화된 기록을 SQLite에 저장/검색하는 클래스와 그 인스턴스.

**`ConversationRAGStore` / `CONVERSATION_RAG_STORE`**
일반 채팅 대화 내용을 ChromaDB로 검색 가능하게 만드는 클래스와 그 인스턴스.

**`DEFAULT_SESSION_SCOPE` / `current_session_scope()`**
지금 이 코드가 "어떤 대화 안에서" 실행되고 있는지 알려주는 값/함수. 대화 밖에서(테스트처럼 직접 함수만 호출할 때) 실행되면 `DEFAULT_SESSION_SCOPE`(`"__direct_tool_call__"`라는 특수 문자열)를 대신 돌려줘요.

**`current_app_date_iso`**
"오늘 날짜"를 표준 형식(YYYY-MM-DD 같은 ISO 형식)의 문자열로 돌려주는 함수. week04 파일엔 import만 돼 있고 아직 실제로 쓰이진 않아요.

**`PROXY_TOKEN` / `.env`**
`.env` 파일에 넣어두는 API 키. 이 프로젝트는 OpenAI에 직접 붙는 게 아니라 강의용 프록시 서버를 거치는데, 그 프록시에 인증하는 키가 `PROXY_TOKEN`이에요.

---

## 5. Python 문법 / 개발 도구

**`ast` (Abstract Syntax Tree, 추상 구문 트리)**
파이썬 코드를 "글자"가 아니라 "문법 구조"로 분석할 수 있게 해주는 표준 라이브러리. `ASSIGNMENT_CHECK_DESIGN.md`에서 "함수 바디가 `...` 하나뿐인지 `ast`로 판별한다"는 게, 코드를 문자열로 억지로 비교하지 않고 진짜 문법 구조를 보고 정확하게 판별하겠다는 뜻이에요.

**`StructuredTool` / `.func`**
`@tool` 데코레이터가 원래 함수를 감싸서 만드는 LangChain 객체 이름이 `StructuredTool`이에요. 그 객체 안에 들어있는 "원래 파이썬 함수"를 꺼내려면 `.func` 속성을 봐야 합니다.

**Pydantic / `Field(ge=..., le=...)`**
Pydantic은 "데이터가 정해진 규칙(타입, 범위 등)에 맞는지 검증"해주는 라이브러리. `Field(ge=1, le=20)`은 "이 값은 1 이상 20 이하여야 한다(ge=greater or equal, le=less or equal)"는 뜻이에요.

**exit code**
프로그램이 끝날 때 운영체제에 알려주는 숫자. 관례상 `0`은 "성공", `0`이 아닌 값(보통 `1`)은 "실패"를 의미해요. 체크 스크립트가 "실패시 exit 1"이라고 한 게 이 뜻입니다.

**CLI (Command Line Interface)**
터미널에서 명령어로 실행하는 방식의 프로그램. `uv run python checks/tool_inventory.py`처럼 터미널에 직접 치는 형태를 말해요.

**`uv run python ...`**
`uv`(패키지 매니저)가 관리하는 가상환경 안에서 파이썬 스크립트를 실행하라는 명령.

**`.gitignore`**
git이 "이 파일/폴더는 버전 관리 대상에서 빼라"고 지정해두는 설정 파일. `checks/logs/`를 `.gitignore` 대상으로 하자는 건, 로그 파일은 저장소에 커밋하지 않겠다는 뜻이에요.

---

## 6. 검증/체크 관련

**정적 검사 vs 동적 검사**
정적 검사는 "코드를 실제로 실행하지 않고" 코드 자체(문법/구조)만 보고 문제를 찾는 것. 동적 검사는 "실제로 프로그램을 돌려보면서" 결과를 확인하는 것. Tier 1(스텁 탐지)이 정적, Tier 2(실제 LLM 호출)가 동적입니다.

**골든 케이스 (golden case)**
"이 입력을 넣으면 이런 결과가 나와야 정상이다"라고 미리 정해둔 정답 세트. 이 정답 세트를 자동으로 돌려보며 실제 결과와 비교하는 테스트 방식을 "골든 케이스 테스트"라고 불러요.

**verify (검증)**
어떤 작업을 하고 나서 "진짜로 의도한 대로 됐는지" 확인하는 과정 전반을 가리키는 말로 씁니다.

---

## 7. 추가 질문 답변

### Q1. ChromaDB는 자동으로 임베딩을 만들어주나? 완전 동떨어진 질문을 하면 "그나마 가장 가까운" 엉뚱한 결과가 정답처럼 나오지 않나?

**임베딩 자동화는 맞습니다.** `PersonalReferenceStore`/`ConversationRAGStore`가 컬렉션을 만들 때 `embedding_function=OpenAIEmbeddingFunction(...)`을 등록해두면([fixed/reference_store.py:98-105](fixed/reference_store.py#L98-L105)), 이후 `.add(documents=[...])`로 저장하거나 `.query(query_texts=[...])`로 검색할 때 ChromaDB가 알아서 그 문장을 벡터로 바꿔줍니다. 개발자가 직접 벡터로 변환하는 코드를 짤 필요는 없어요.

**단, "일정"은 임베딩 대상이 아닙니다.** 이 부분이 질문의 전제와 달라서 짚어야 하는데 — Week 3에서 저장한 일정/할일/알림(`AppSQLiteStore`)은 `search_saved_requests`로 검색할 때 ChromaDB/임베딩을 전혀 안 씁니다. `raw_json LIKE '%검색어%'` 같은 **일반 SQL 텍스트 매칭**이에요([fixed/app_store.py:454-476](fixed/app_store.py#L454-L476)). 이 앱에서 실제로 임베딩되는 건 ① 개인 참고자료(`PersonalReferenceStore`)와 ② 일반 채팅 대화(`ConversationRAGStore`) 두 가지뿐입니다.

**"동떨어진 질문에 엉뚱한 결과가 나오는" 문제는 실제로 존재합니다 — 이 코드엔 안전장치가 없어요.** 코드를 다시 확인해봤는데(`fixed/reference_store.py:155-172`, `fixed/conversation_rag_store.py:96-159`), `distance` 값에 대한 임계값(threshold) 검사가 **어디에도 없습니다.** `collection.query(query_texts=[...], n_results=N)`은 "쿼리와 가장 가까운 N개"를 무조건 돌려줍니다 — 그 N개가 실제로 얼마나 가까운지(거리가 1이든 20이든)와 무관하게요. 그러니 말씀하신 시나리오("정답급 거리는 1인데, 완전 동떨어진 질문의 최선 결과가 20")가 실제로 그대로 일어날 수 있고, 이 코드는 그 20짜리 결과를 걸러내지 않고 그냥 반환합니다.

다만 "그게 곧바로 최종 답변에 정답처럼 쓰인다"는 아닙니다 — 왜냐하면:
- hit에는 `distance` 숫자만 있는 게 아니라 실제 `content`(원문)도 같이 딸려가므로, LLM이 그 내용을 읽고 "이건 질문과 상관없는 내용이네"라고 스스로 판단해서 무시할 여지가 있어요. 다만 이건 LLM의 판단력에 의존하는 것이라 **보장되는 안전장치는 아닙니다.**
- 지금 제가 넣은 프롬프트 문구("검색 결과가 없으면 없다고 답하고 내용을 지어내지 않는다")는 "검색 결과가 아예 0개일 때"를 위한 것이지, "검색 결과는 있는데 다 엉뚱할 때"를 막아주진 않아요 — 이 둘은 다른 문제입니다.

**실제로 이 문제를 막으려면** (지금 코드엔 없는, 추가로 만들어야 하는 안전장치들):
1. `search_personal_reference_hits`/검색 함수 안에서 `distance`가 특정 값보다 크면 그 hit을 아예 결과에서 제외하는 임계값 필터를 추가.
2. 또는 system prompt에 "hit의 distance가 너무 크면(관련성이 낮으면) 그 내용을 근거로 쓰지 말라"는 지시문 추가.
3. 다만 "얼마 이상이면 멀다고 볼지" 기준값은 지금 이 임베딩 모델/거리 방식(ChromaDB 기본값은 별도 설정이 없으면 L2 거리이고, 코드에 `hnsw:space` 같은 거리 방식 지정이 없어 기본값을 그대로 씀)에서 실제 질문 여러 개를 넣어보고 "관련 있는 질문의 거리 분포 vs 관련 없는 질문의 거리 분포"를 직접 재봐야 정할 수 있어요 — "1이면 정답, 20이면 오답" 같은 구체적 숫자는 이 프로젝트에서 실측된 적이 없어서 지어낼 수 없습니다. (참고로 위 예시에서 쓰신 1/20이라는 숫자는 질문의 예시일 뿐, 실제 이 임베딩 모델의 거리값 통계는 아니에요.)

### Q2. lazy sync는 왜 쓰나? 장단점?

`ConversationRAGStore.sync_from_sqlite(sqlite_store)`가 검색 직전에 호출되는 방식이 "lazy(게으른) sync"입니다([fixed/conversation_rag_store.py:62-94](fixed/conversation_rag_store.py#L62-L94)).

**장점**
- 별도의 백그라운드 동기화 프로세스/스케줄러가 필요 없음 — 관리 포인트가 하나 줄어듦
- 아무도 대화 검색을 안 하면 동기화 자체가 아예 실행되지 않음 — 안 쓰는 기능을 위해 계속 도는 작업이 없음
- 검색 시점 기준으로는 항상 "방금 최신 상태"가 보장됨(검색 직전에 맞추므로)
- 이 프로젝트의 실제 구현은 "매번 전체를 다시 임베딩"하지 않고 `source_hash`로 변경분만 골라 upsert하고, 없어진 대화만 delete함([fixed/conversation_rag_store.py:69-87](fixed/conversation_rag_store.py#L69-L87)) — 그래서 lazy여도 매번 전체 재계산하는 낭비는 없음

**단점**
- 검색할 때마다 "동기화 필요한지 확인하는 작업"(SQLite 전체 대화 조회 + 해시 비교)이 검색 앞에 끼어들어서, 매 검색마다 약간의 지연(latency)이 추가됨
- 새로 생기거나 바뀐 대화가 많으면, 그 임베딩 API 호출 비용/시간이 "검색하는 바로 그 순간"에 한꺼번에 몰림 — 검색하려는 사용자가 그 비용을 그대로 기다려야 함
- 동기화 도중 오류가 나면 그 검색 결과가 일부만 최신화된 상태로 나갈 수 있음

**대안(이 프로젝트엔 없는 방식)**: 메시지를 SQLite에 저장하는 바로 그 순간 ChromaDB도 같이 업데이트하는 "즉시(eager) sync". 이러면 검색은 항상 빠르지만, 검색을 한 번도 안 하는 경우에도 매 메시지마다 추가 작업이 들어가는 게 단점이에요. 이 프로젝트가 lazy를 택한 이유는 "학생용 로컬 앱이라 트래픽이 적고, 검색이 실제로 필요할 때만 비용을 쓰는 게 더 합리적"이라는 판단으로 보입니다.

### Q3. flat 구조 vs 중첩 구조 — 장단점, 언제 쓰나?

**flat 구조** (`{"id": .., "title": .., "tags": ..}` — 다 한 층에)
- 장점: 접근이 단순(`hit["title"]`), 코드가 짧아짐, JSON도 더 가벼움
- 단점: 필드가 많아질수록 "이게 핵심 데이터인지 부가정보인지" 구분이 안 됨, 여러 출처의 hit을 한 형식으로 통일하기 어려움(출처마다 필드가 제각각이 되기 쉬움)
- 이 프로젝트에서 쓰인 곳: `search_saved_request_rows` — SQLite row를 그대로(pass-through) 반환하므로 flat. 이 tool 하나만 쓰는 결과라 "여러 출처 공통 포맷"을 맞출 필요가 없었음

**중첩(nested) 구조** (`{"id": .., "content": .., "distance": .., "metadata": {"title": .., "tags": ..}}`)
- 장점: "핵심 3total"(id/content/distance)과 "부가 설명"(metadata)이 명확히 분리됨 → 나중에 metadata 필드가 늘어나도(예: 작성일, 출처 등 추가) 핵심 구조(top-level)는 안 바뀜. 여러 종류의 RAG 검색 결과(참고자료 hit, 대화 hit 등)를 같은 틀(id/content/distance/metadata)로 통일하기 쉬움 — 실제로 이 프로젝트의 "hit" 계약이 이 형태를 요구하는 이유도 이거예요(가이드가 여러 검색 tool에 공통 포맷을 원함)
- 단점: 접근이 한 단계 더 필요(`hit["metadata"]["title"]`), 코드가 살짝 길어짐, `metadata`에 있는 필드가 없을 수도 있어서 `.get(..., 기본값)` 처리를 빼먹으면 에러 남

**언제 쓰나 요약**: 여러 출처/여러 tool이 "같은 모양의 결과"를 내놔야 하고 그 모양이 나중에 계속 확장될 가능성이 있으면 중첩(metadata 분리)이 유리하고, 딱 한 곳에서만 쓰고 확장 계획도 없는 단순한 데이터 전달이면 flat이 더 간단하고 좋습니다. `search_personal_references`가 중첩, `search_saved_requests`가 flat인 이유가 정확히 이 차이입니다.
