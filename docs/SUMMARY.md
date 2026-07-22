# 요약 (원본: WEEK04_IMPLEMENTATION_PLAN.md / WEEK04_MAIN_TASK_EXECUTION_PLAN.md / ASSIGNMENT_CHECK_DESIGN.md)

키워드 압축본. 세부 근거/코드/줄번호는 각 원본 문서 참고.

---

# 1. WEEK04_IMPLEMENTATION_PLAN.md 요약

## 0. 핵심
- Week3=저장 / Week4=검색(RAG)
- 진짜 목표: RAG 자체 X, **출처별 tool 분리** O
- 출처 3곳: 참고자료(Chroma·PersonalReferenceStore·REFERENCE_STORE) / 저장기록(SQLite·AppSQLiteStore·SQLITE_STORE) / 채팅발화(Chroma·ConversationRAGStore·CONVERSATION_RAG_STORE)
- fixed/ 쪽 store 메서드 대부분 구현완료 → 학생 할일 = ① 메서드 올바르게 호출 + ② 결과를 tool계약(JSON top-level 키) 모양으로 포장. 새 알고리즘 X

## 1. 구현순서
1. add_personal_reference_dict → add_personal_reference (메인)
2. search_personal_reference_hits → search_personal_references (메인)
3. search_saved_request_rows → search_saved_requests (메인)
4. week04_prompt_parts() 지시문 추가 (메인, 함수구현만큼 중요)
5. search_conversation_messages 계열 (추가과제)
6. search_nana_memory (선택, skip 가능)
- 순서 강제 X (뒷단계가 앞단계결과 의존 안함) but 이 순서 = 매단계 끝날때마다 앱으로 바로 확인 가능

## 2. 단계별 스케치

**2-1 add_personal_reference**
- PersonalReferenceStore.add_personal_reference(title,content,tags) 이미구현 (reference_id/title/content/tags/backend 반환)
- 할일: tags None→[] 정규화만
- payload top-level: `reference_backend`, `reference`

**2-2 search_personal_references**
- ⚠ store반환 flat({id,title,content,tags,distance}) ≠ 가이드계약(id,content,distance,**metadata**{title,tags}) → reshape 필요
- 설계판단: tags "a,b"문자열 vs 리스트 → 리스트 추천 (add쪽 입력=list라 round-trip 일관)
- payload top-level: `hits`

**2-3 search_saved_requests**
- AppSQLiteStore.search_saved_requests(query,kind=None,limit) 이미구현, LIKE검색, 결과없음→[]
- reshape 불필요, pass-through
- payload top-level: `rows`

**2-4 week04_prompt_parts() — 지금 TODO주석만, 지시문 0줄**
- 함수4개 다 구현해도 prompt 비면 LLM이 tool선택기준 자체를 모름 = **메인과제 포함 작업**
- 넣을내용: 취향/메모질문→search_personal_references / 저장기록질문→search_saved_requests(Week3 personal_list_saved_schedules와 다른경로 구분) / (추가과제시)잡담질문→search_conversation_messages / 복수tool 동시사용 가능 / assistant발화만으로 사실확정 금지(가이드79번줄 명시)
- current_app_date_iso: import만, 미사용 → 날짜문장 넣고싶으면 여기, 안써도 무방

**2-5 (추가과제) search_conversation_messages 계열 — 가장 손 많이감**
- ConversationRAGStore.search() 파라미터2개 상호배타: `conversation_id`(명시필터) / `exclude_conversation_id`(conversation_id 없을때만 제외필터) — 조건문(`if not conversation_id and exclude_conversation_id...`)상 동시의미 X
- 매핑: tool의 conversation_id 있음→store conversation_id로 / None→current_session_scope()를 store exclude_conversation_id로
- current_session_scope() 대화밖에선 `"__direct_tool_call__"`(DEFAULT_SESSION_SCOPE) 반환 → 실제대화ID로 저장될일 없어 exclude에 넣어도 안전
- 반환: hits/rows 동일값 + context(context_from_hits) + rag_backend(backend_info) + sync(sync_from_sqlite결과)

**2-6 search_nana_memory — 지금 안건드려도 O**
- 가이드: 학생핵심구현대상 4개에 미포함, "참고코드/호환용"
- week04_tools()에도 미포함 → 검증영향 X

## 3. 검증 체크리스트
- [ ] run.sh --week4 실행
- [ ] 참고자료 추가 → trace: add_personal_reference 호출, reference_backend/reference 키 확인
- [ ] 관련질문 → trace: search_personal_references 호출, top-level=hits 확인
- [ ] 저장기록질문 → trace: search_saved_requests 호출, top-level=rows 확인
- [ ] (추가) 잡담질문 → search_conversation_messages 호출, 현재대화 제외 확인
- [ ] (추가) conversation_id 명시 → 그 대화로만 좁혀지는지 확인

## 4. 흔한 실수
- top-level 키 오타/누락 (hits/rows = LLM이 프롬프트에서 참조하는 실계약)
- search_personal_reference_hits reshape 누락 → metadata 키 자체 없음 = 계약위반
- conversation_id + exclude_conversation_id 동시채움 → store조건문상 conversation_id 있으면 exclude로직 자체를 안탐
- week04_prompt_parts() 미작성 → tool은 정상동작해도 LLM이 애초에 선택 안함(3주차 "서술문 vs 지시문" 이슈 동일유형)

---

# 2. WEEK04_MAIN_TASK_EXECUTION_PLAN.md 요약

## 범위: week04_retrieve_nanas_memory.py 5곳만
1. add_personal_reference_dict (219-229)
2. search_personal_reference_hits (232-241)
3. search_saved_request_rows (244-253)
4. 3개 tool본문 (283-304)
5. week04_prompt_parts() (350-356)
- fixed/, 타주차파일 = 손 안댐

## 구현전 확정결정 3가지
- **① ok/tool_name 키 → 미포함.** Week3(tool_result헬퍼)와 달리 Week4가이드는 이 키 요구 X, 이 파일엔 그런 헬퍼 자체 없음(json_payload만 有) → 가이드에 없는키 임의추가 = simplicity first 위반 → 가이드문구 그대로 필요키만 반환
- **② tags 문자열 vs 리스트 → 리스트로 되돌림.** round-trip 일관성 위해 (PersonalReferenceStore 내부 ","join저장 → 조회시 split(",") , 빈문자열→빈리스트)
- **③ safe_limit() 호출 = Pydantic(ge/le)과 중복 → 그래도 가이드대로 호출.** 정상경로에선 죽은방어코드(3주차 `members if not None else []`와 동일유형) BUT 가이드 명시지시 → 요청받은거 따르는것이므로 유지

## 단계별계획 (Karpathy 포맷)
1. add_personal_reference_dict+add_personal_reference → verify: 임시Chroma dir로 store만들어 참고자료추가, dict에 reference_id/title/content/tags/backend 채워지는지
2. search_personal_reference_hits+search_personal_references → verify: 같은임시store 검색, hit≥1, id/content/distance/metadata(title,tags:list) 모양
3. search_saved_request_rows+search_saved_requests → verify: 실DB 읽기전용검색이라 그대로호출 안전, 에러없이 list(빈리스트포함)반환
4. week04_prompt_parts() 채움 → verify: week04_system_prompt() 에러없이생성, "search_personal_references"/"search_saved_requests" 이름이 프롬프트본문에 실제언급되는지
5. 전체모듈 import확인 → verify: `python -c "import student_parts.week04_retrieve_nanas_memory"` 예외없이종료

## 검증방식 비고
- .env PROXY_TOKEN 유효 사전확인완료 → 1-3번 실호출로 검증
- 참고자료추가(1번) = 실data/chroma 오염방지 위해 **임시디렉터리에 별도 store인스턴스**로 검증후 삭제
- SQLite검색(3번) = 읽기전용이라 실DB 그대로 호출해도 무해
- 자동테스트하네스 없음(README명시) → 임시스크립트로 직접호출검증, 검증후 스크립트 삭제
- 최종 trace확인(run.sh --week4)은 사용자가 직접 채팅으로

---

# 3. ASSIGNMENT_CHECK_DESIGN.md 요약

## 배경: 실패유형 2가지, 검증방법 다름
1. **조립회귀** (예: week03 personal_create_schedule 스텁바꿔치기) → LLM 호출없이 코드만 봐도 판별 O = **정적검사** 대상
2. **의도전달실패** (함수구현O, prompt지시 X → LLM이 tool 안고름, "서술문vs지시문" 이슈) → 실제LLM 호출해야만 판별 O = **동적검사** 대상
- → 한도구로 둘다처리 X, **Tier1(정적/무료)+Tier2(동적/비용)** 2단설계

## Tier1 — 정적 조립검사 (무료, API호출 X)
검사항목:
- 스텁탐지: weekNN_tools() 반환 tool의 원본함수 바디 = `...`(Ellipsis) 단독인지 ast파싱 판별. `@tool`감싼 StructuredTool은 `.func`로 원본추출
- 주차간 회귀탐지: weekN_tools() vs week(N-1)_tools() 비교, 이전엔 있던이름 tool이 이번주차서 스텁으로 퇴화했는지(=실제겪은버그와 동일케이스)
- 이름 중복/누락: 같은tool이름 2번등록 / 가이드"구현대상"함수명이 실제tool목록서 누락
- prompt조립확인: weekNN_prompt_parts() 예외없이생성 + 그주차 새구현(비스텁)tool이름이 최종system prompt문자열에 실제등장하는지(포함여부) = "구현은했는데 prompt에 언급없음" 케이스 포착

안전성:
- **LLM 전혀 부르지 X → API키/비용 없이도 실행 O**, 몇초내 완료
- import만으로 검사종료 → 실SQLite/Chroma데이터 부작용 X
- **코드수정마다(커밋,PR전) 매번 돌려도 됨**

## Tier2 — 동적 agent호출 trace검사 (API비용 발생)
케이스정의(JSON): `{week, prompt, expect_tool_calls:[...], expect_json_keys:{tool명:[키,...]}}`

실행절차:
1. build_week_agent()로 실제agent생성
2. agent.invoke({"messages":[{"role":"user","content":prompt}]}) 실LLM호출
3. 결과 → `extract_agent_events(result)`(앱이 실제쓰는 동일코드, tool_call/tool_result 이벤트리스트 추출)
4. 검증: expect_tool_calls 전부 실제호출됐는지 / 각tool의 tool_result content(이미JSON파싱) top-level키 = expect_json_keys 일치하는지
- = "골든케이스" 방식, 멘토 언급 golden_cases.py/run_golden.py와 동일개념(현저장소엔 실존 X 확인됨, 같은이름·개념으로 신규제작 제안)

⚠ 부작용 — 쓰기tool 주의:
- "일정저장해줘"/"참고자료추가해줘" 유도 = 실data/kanana_app.sqlite3, data/chroma에 테스트데이터 남음
- **옵션A**: 쓰기케이스 제외, 조회/검색tool만 (안전 / but 쓰기tool의 실LLM선택여부 검증불가)
- **옵션B**: 격리된 임시DB/Chroma경로로 실행 (쓰기tool도 검증가능 / but build_week_agent()가 전역SQLITE_STORE/REFERENCE_STORE 참조 → 완전격리엔 monkeypatch 필요)
- **추천: A로 시작** (지금까지 겪은문제 전부 "조회/tool선택" 이슈, "쓰기데이터오염" 이슈 아니었음). 필요커지면 B로 확장

비용성격:
- 케이스1개당 LLM호출1회(+검색tool선택시 임베딩API 추가) → Tier1과달리 **매저장마다 자동실행 X, PR전 수동실행용**

## 파일배치안
```
checks/
  tool_inventory.py   # Tier1: 스텁/회귀/이름검사 로직+CLI
  golden_cases.py      # Tier2: 주차별 케이스목록
  run_golden.py        # Tier2: 케이스실행기
```
- checks/ = student_parts/(학생코드)도 fixed/(강사기준코드)도 아닌 "검증전용" 위치 명확분리
- run.sh 안건드림 (앱실행/검증 = 별개 진입점)

## 실행법(제안)
```
uv run python checks/tool_inventory.py       # Tier1만, 기본/무료/항상가능
uv run python checks/run_golden.py --week 4  # Tier2, 지정주차만, API비용발생
uv run python checks/run_golden.py           # Tier2, 전체주차
```

## 출력형식
- PASS/FAIL 한줄씩 + 마지막요약(N개실패 or ALL CHECKS PASSED) + 실패시 exit1
- 로그파일저장 = 기본X(콘솔출력만), 필요시 checks/logs/(.gitignore) 추가는 다음단계로 보류

## 구현전 미확정 (사용자 결정 필요)
1. 범위: Tier1만 먼저 vs Tier1+2 한번에? (Tier2=실API비용 차이)
2. Tier2 케이스대상: 옵션A(조회/검색tool중심, 쓰기tool제외)로 시작 동의?
