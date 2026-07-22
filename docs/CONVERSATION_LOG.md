# 대화 로그

Claude와 나눈 작업 대화를 시간순으로 요약해 기록하는 문서입니다. 새 요청/작업이 있을 때마다 아래에 항목을 추가해 최신 상태로 유지합니다.

## 현재 상태 (마지막 갱신 기준)

- 브랜치: `yongbin/week4` (base는 `yongbin/final`)
- Week 3: 메인+추가과제 전부 구현, PR #74에 반영·머지 완료
- Week 4: 메인과제 중 `add_personal_reference`/`search_personal_references`/`search_saved_requests` 3개 tool 구현 완료. `week04_prompt_parts()`는 사용자가 직접 작성하기로 해 TODO 상태로 되돌려둠(의도적). 추가과제(`search_conversation_messages` 계열)는 미착수
- `checks/tool_inventory.py` (Tier 1 정적 조립 검사) 구현 완료, 실행 확인함 — week1-3 전부 PASS, week4는 prompt 미작성으로 FAIL 1건(의도된 상태)
- `ASSIGNMENT_CHECK_DESIGN.md`의 Tier 2(실제 agent 호출 골든 케이스)는 아직 미구현
- 앱이 `./run.sh --week4`로 백그라운드 실행 중 (포트 7860, PID 20840) — 사용자가 직접 브라우저에서 채팅 테스트 예정

## 로그

1. **멘토 PR #74 리뷰 검토** — `week03_build_nanas_logbook.py`에 대한 멘토(GitJIHO) 코멘트 2건 확인. ① `week03_tools()`가 아직 미구현 스텁인 `personal_create_schedule`로 Week 1의 정상 동작 tool을 무조건 바꿔치기하는 회귀 확인. ② "이번 주차는 저장/조회까지"라는 프롬프트 문구가 서술문일 뿐, 수정/삭제 tool 호출 자체를 막는 지시문은 아니라는 점을 코드로 확인.

2. **Week 3 추가과제 전체 구현 + 리뷰 반영, PR #74 반영** — `unwrap_legacy_payload`, `_save_input_from`, `save_structured_request_payload`, `_delete_saved_schedules`, `structured_request_from_week01_schedule`, `personal_create_schedule`, `personal_update_saved_schedule`, `personal_delete_saved_schedules` 전부 구현. `week03_prompt_parts()`의 서술문을 실제 지시문으로 교체. 로컬 테스트 30개 통과 확인 후 `yongbin/week3` 브랜치에 커밋(Co-Authored-By 표기 제거 요청 반영해 amend + force-push)해 PR #74에 반영.

3. **CLAUDE.md 생성 (`/init`)** — 저장소 분석 후 명령어(`run.sh`, `uv`, trace 기반 수동 검증), 아키텍처(`app.py`→`agent_runtime`→`week_agent_registry`→`student_parts`), 주차별 모듈 계약(`weekNN_tools`/`weekNN_prompt_parts`/`build_week_agent`), 데이터 계층(`AppSQLiteStore`/ChromaDB/`CONFIG` 싱글턴), tool 구현 패턴, git 워크플로를 정리해 `kangwon-clone/CLAUDE.md` 작성.

4. **`KTC_WEEKLY_SYNC.md` 저장 + 4주차 강의자료 동기화 실행** — 사용자가 붙여넣은 "강의자료 최신화" 절차 문서를 저장소에 `KTC_WEEKLY_SYNC.md`로 저장. 문서에 정의된 diagnose→merge→verify→finish 절차를 그대로 실행해 `main`의 신규 4주차 자료를 `yongbin/final`에 충돌 없이 머지, push 후 `yongbin/week4` 브랜치 생성. (진행 전 미커밋 상태였던 `WEEK02_REQUIREMENTS.md`는 사용자 확인을 받아 커밋 후 진행)

5. **CLAUDE.md 적용 범위 질문 답변** — `CLAUDE.md`는 파일이 위치한 폴더(`kangwon-clone`) 안에서 작업할 때만 적용된다는 점 확인.

6. **아키텍처/개념 전체 설명** — CLAUDE.md 요약 6개 항목(명령어/아키텍처/모듈계약/데이터계층/tool 패턴/git 워크플로)을 요청에 따라 하나씩 풀어서 설명(uv, trace JSON, `week_agent_registry`, Pydantic `args_schema`, ChromaDB, `CONFIG` 싱글턴, git rebase/force-push 위험성 등).

7. **Week 4 과제 내용 설명** — `week04_retrieve_nanas_memory.py` 전체를 읽고 메인과제(`add_personal_reference`/`search_personal_references`/`search_saved_requests`)와 추가과제(`search_conversation_messages`/`search_nana_memory`)를 구분해 설명.

8. **`WEEK04_IMPLEMENTATION_PLAN.md` 작성** — Week 4 구현 설계 문서(구현 순서, 단계별 스케치, 검증 체크리스트, 흔한 실수)를 코드 변경 없이 작성.

9. **Karpathy 가이드라인 스킬 로드** — 이후 작업에 "생각 먼저 / 단순함 우선 / 외과적 변경 / 목표 기반 검증" 원칙 적용 시작.

10. **`WEEK04_MAIN_TASK_EXECUTION_PLAN.md` 작성 + 메인과제 구현** — 실행 전 설계 결정 3가지(JSON payload에 `ok`/`tool_name` 키 미포함, 참고자료 검색 결과 `tags`를 리스트로 round-trip, `safe_limit()` 호출은 Pydantic 검증과 중복이어도 가이드 지시대로 유지)를 확정한 뒤 `add_personal_reference`/`search_personal_references`/`search_saved_requests` 3개 tool과 `week04_prompt_parts()` 구현. 임시 검증 스크립트로 실제 함수 호출 검증(9개 체크 통과) 후 스크립트는 삭제.

11. **`ASSIGNMENT_CHECK_DESIGN.md` 작성** — 과제 구현 확인용 체크 도구 설계. Tier 1(정적 스텁/회귀 검사, 무료·즉시)과 Tier 2(실제 agent 호출 골든 케이스, API 비용 발생) 2단 구조로 제안. 아직 코드 미구현, 범위(Tier1만 vs Tier1+2)는 사용자 결정 대기.

12. **문서 압축 + `docs/` 폴더 정리** — 위 3개 설계 문서를 키워드 형식으로 압축한 `docs/SUMMARY.md` 작성, 원본 3개 문서와 함께 새로 만든 `docs/` 폴더로 이동.

13. **이 대화 로그 문서 생성** — `docs/CONVERSATION_LOG.md` 작성. 앞으로 대화가 이어질 때마다 위 "현재 상태"와 "로그" 섹션을 갱신.

14. **`docs/GLOSSARY.md` 단어장 작성** — `docs/SUMMARY.md`에 나오는 전문용어를 6개 카테고리(AI/LLM 개념, 저장소/DB, 코드·설계 용어, 프로젝트 전역변수, Python 문법/도구, 검증 관련)로 정리해 초보자 기준으로 설명하는 단어장 문서 작성.

15. **임베딩/lazy sync/flat vs 중첩구조 질문 답변 (`docs/GLOSSARY.md` 7장 추가)** — ① ChromaDB 임베딩은 자동이지만 Week3 일정 검색은 임베딩이 아니라 SQL LIKE 매칭임을 정정, distance 임계값 필터링이 코드에 전혀 없어 "동떨어진 질문에도 그나마 가까운 결과가 그대로 반환되는" 설계 공백을 코드 확인 후 인정. ② lazy sync 장단점(관리포인트 감소·필요시만 비용 vs 검색시 지연·비용 집중) 정리. ③ flat vs 중첩 구조 장단점 및 선택 기준(공통 포맷 필요 여부) 정리.

16. **Tier 1 정적 조립 검사 구현 + Week4 프롬프트 되돌리기 + 진행보고서 작성** — `checks/tool_inventory.py` 구현(스텁 탐지·회귀 탐지·이름 중복·prompt 언급 검사, ast 기반). 실행해서 `add_personal_reference`가 프롬프트에 언급 안 된 실제 문제를 발견. 이후 사용자 요청대로 `week04_prompt_parts()`를 사용자가 직접 쓰도록 TODO로 되돌림(3개 tool 미언급 FAIL은 의도된 상태). `docs/WEEK04_TIER1_REPORT.md`에 전체 과정·결과·문서별 줄번호 참조를 정리해 보고서로 작성.

17. **구현 범위 티어 확인 질문 답변** — 지금까지 구현한 3개 함수+3개 tool 본문이 가이드 주석 기준 전부 `[메인]` 태그임을 파일 내 주석 줄번호로 확인. `[공통]` 태그가 붙은 유틸/조립 함수들은 원래부터(작업 시작 전부터) 완성돼 있던 것이지 이번에 구현한 게 아님을 구분. `week04_prompt_parts()`도 `[공통]` 태그지만 유일하게 구현이 필요했던 항목이며 지금은 의도적으로 TODO 상태임을 재확인.

18. **`week04_prompt_parts()` 내용 추천 + 여러 항목으로 쪼개도 되는지 질문 답변** — 프롬프트에 들어갈 내용 추천(3개 tool 역할 구분, Week3 `personal_list_saved_schedules`와의 차이, 복수 tool 허용, 결과 없을 때 안전장치, distance 임계값 부재 관련 경계 문구 제안). `join_system_prompt()` 실제 코드(`week01_wake_up_nana.py:34-41`) 확인해 "긴 문자열이라 누락된다"는 우려는 기계적 근거가 없음(단순 `"\n\n".join`)을 설명하되, LLM이 긴 문단 속 지시를 놓치기 쉬우므로 여러 짧은 항목으로 쪼개는 게 좋은 습관이라는 점과 `week03_prompt_parts()`의 기존 선례를 근거로 제시.

19. **`run.sh --week4` 실행 + 테스트케이스 6개 추천** — `run` 스킬로 앱을 백그라운드 실행(포트 7860), curl로 정상 기동 확인(이 환경엔 브라우저 자동화 도구가 없어 실제 채팅 구동은 사용자가 직접 진행). 포트 번호 질문에 7860 답변. Week4 검증용 테스트케이스 6개 추천(참고자료 추가/검색, 저장기록 검색, 결과 없음 케이스, distance 임계값 부재 직접 관찰용 동떨어진 질문, 복수 tool 동시 필요 질문) — 프롬프트 작성 전/후 비교해보라고 안내.

20. **대화 로그 최신화 여부 질문 답변** — 17-19번 항목이 누락돼 있던 걸 확인하고 추가.
