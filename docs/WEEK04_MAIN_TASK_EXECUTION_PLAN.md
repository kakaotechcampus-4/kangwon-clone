# Week 4 메인과제 실행 계획

`WEEK04_IMPLEMENTATION_PLAN.md`(설계 문서)를 실제로 적용하기 위한 실행 계획입니다. **이번 패스는 메인과제 범위만** 다룹니다 — 추가과제(`search_conversation_messages` 계열)는 손대지 않습니다.

## 범위

`student_parts/week04_retrieve_nanas_memory.py`에서 다음 4곳만 수정합니다:

1. `add_personal_reference_dict` (219-229번 줄)
2. `search_personal_reference_hits` (232-241번 줄)
3. `search_saved_request_rows` (244-253번 줄)
4. `add_personal_reference` / `search_personal_references` / `search_saved_requests` tool 본문 (283-304번 줄)
5. `week04_prompt_parts()` (350-356번 줄)

그 외 파일(`fixed/`, 다른 주차 파일)은 건드리지 않습니다.

## 구현 전 확정해야 할 결정 사항

`WEEK04_IMPLEMENTATION_PLAN.md`에 "설계 판단 필요"로 남겨둔 부분을 실제 코드로 옮기려면 하나로 확정해야 합니다. 아래처럼 정하고 진행합니다.

**① JSON payload에 `ok`/`tool_name` 키를 넣을지 여부 → 넣지 않습니다.**
Week 3(`week03_build_nanas_logbook.py`)는 `tool_result()` 헬퍼로 모든 tool에 `ok`/`tool_name`을 강제하지만, Week 4 가이드 원문은 이 두 키를 요구하지 않습니다 — "reference_backend와 reference가 있는 JSON payload", "top-level `{"hits": [...]}`", "top-level `{"rows": [...]}"} 라고만 되어 있고, 이 파일엔 `tool_result()` 같은 헬퍼 자체가 없습니다(`json_payload()`만 있음). 가이드에 없는 키를 임의로 추가하는 건 이번 카르파시 가이드라인의 "simplicity first"(요청 안 한 것 추가 금지)에 어긋나므로, **가이드 문구 그대로 필요한 키만 반환**합니다.

**② 참고자료 검색 결과의 `tags`를 문자열로 둘지 리스트로 되돌릴지 → 리스트로 되돌립니다.**
`add_personal_reference`가 `tags: list[str]`을 받아 저장하므로, 검색 결과도 리스트로 돌아와야 호출자 입장에서 입출력 타입이 일관됩니다. `PersonalReferenceStore`가 내부적으로 `","`.join()해서 저장하므로 조회 시 `.split(",")`로 되돌리되, 빈 문자열이면 빈 리스트로 처리합니다.

**③ `safe_limit()` 호출이 Pydantic 검증과 중복 아닌가? → 그래도 가이드대로 호출합니다.**
`SearchPersonalReferencesInput`/`SearchSavedRequestsInput`이 이미 `Field(ge=1, le=...)`로 범위를 검증하므로, tool 본문에서 `safe_limit()`을 또 부르는 건 정상 호출 경로에서는 사실상 죽은 방어 코드입니다(3주차 리뷰에서 확인했던 `members if not None else []`와 같은 종류). 그런데 이건 가이드가 "top_k/limit 보정은 이 파일의 `safe_limit()`를 사용해 tool 안에서 처리합니다"라고 명시적으로 지시한 부분이라, 요청받지 않은 걸 빼는 게 아니라 요청받은 걸 따르는 것이므로 그대로 넣습니다.

## 단계별 계획 (Karpathy 가이드라인 형식)

```
1. add_personal_reference_dict + add_personal_reference 구현
   → verify: 임시 ChromaDB 디렉터리로 PersonalReferenceStore를 만들어 실제로 참고자료 하나를 추가하고
     반환 dict에 reference_id/title/content/tags/backend가 채워지는지 확인

2. search_personal_reference_hits + search_personal_references 구현
   → verify: 같은 임시 store에서 방금 추가한 참고자료를 검색해 hit이 하나 이상 나오고,
     각 hit이 id/content/distance/metadata(title,tags: list) 모양인지 확인

3. search_saved_request_rows + search_saved_requests 구현
   → verify: 실제 앱 SQLite(data/kanana_app.sqlite3)에 대해 읽기 전용 검색이므로 그대로 호출해도 안전 —
     쿼리 실행이 에러 없이 리스트(빈 리스트 포함)를 반환하는지 확인

4. week04_prompt_parts() 채우기
   → verify: week04_system_prompt()를 호출해 문자열이 에러 없이 만들어지고,
     "search_personal_references"/"search_saved_requests" 두 tool 이름이 프롬프트 본문에 실제로 언급되는지 확인

5. 전체 모듈 import 확인
   → verify: `python -c "import student_parts.week04_retrieve_nanas_memory"` 가 예외 없이 끝나는지 확인
```

1-3번 검증은 실제 `.env`의 PROXY_TOKEN(임베딩 API 키)이 유효한 걸 미리 확인했으므로 실제 호출로 검증합니다. 단, 참고자료 추가(1번)는 학생의 실제 `data/chroma` 컬렉션을 건드리지 않도록 **임시 디렉터리에 별도 `PersonalReferenceStore` 인스턴스를 만들어서** 검증하고 끝나면 지웁니다(실 데이터에 테스트용 참고자료가 남지 않게 하기 위함). SQLite 검색(3번)은 읽기 전용이라 실제 DB에 그대로 호출해도 부작용이 없습니다.

이 저장소에는 자동 테스트 하네스가 없으므로(README 명시), 위 검증은 앱을 통하지 않고 함수를 직접 호출하는 방식의 임시 스크립트로 진행하고, 스크립트는 검증 후 삭제합니다. 최종적으로 `./run.sh --week4`를 통한 trace 확인은 사용자가 직접 채팅으로 해보시는 걸 권장합니다(검증 체크리스트는 `WEEK04_IMPLEMENTATION_PLAN.md` 3장 참고).
