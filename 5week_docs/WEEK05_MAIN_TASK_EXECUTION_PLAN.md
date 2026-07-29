# Week 5 메인과제 실행 계획

`WEEK05_IMPLEMENTATION_PLAN.md`(설계 문서)를 실제로 적용하기 위한 실행 계획입니다. **이번 패스는 메인과제 범위만** 다룹니다 — 추가과제(`create_shared_schedule`/`delete_shared_schedule`)는 손대지 않습니다.
(docs/WEEK04_MAIN_TASK_EXECUTION_PLAN.md와 같은 구성)

## 범위

`student_parts/week05_load_kanas_past_conversations.py`에서 다음만 수정합니다:

1. `_personal_schedules_for_current_scope` (helper, 189-193번 줄)
2. `_collect_member_schedules` (helper, 276-286번 줄)
3. `search_previous_conversations` tool 본문 (289-298번 줄)
4. `load_conversation_messages` tool 본문 (301-306번 줄)
5. `extract_schedules_from_history` tool 본문 (309-314번 줄)
6. `list_shared_schedules` tool 본문 (345-356번 줄)
7. `collect_member_schedules` tool 본문 (359-364번 줄)
8. `week05_prompt_parts()` (388-394번 줄)

그 외 파일(`fixed/`, `mcp_server/`, 다른 주차 파일)은 건드리지 않습니다. 추가과제 tool(`create_shared_schedule`/`delete_shared_schedule`, 317-342번 줄)은 이번 패스에서 스텁으로 둡니다 — 단, 스텁 노출 문제를 피하려면 §"결정 사항"의 ②를 참고.

## 구현 전 확정해야 할 결정 사항

**① `call_mcp_tool_sync`(str) vs `call_external_tool_payload`(dict) 반환 처리 → 가이드 그대로.**
`load_conversation_messages`만 `call_external_tool_payload` → dict → `json_payload()`로 감싸고, 나머지 4개 조회 tool은 `call_mcp_tool_sync` → 문자열을 **그대로 return**합니다. 문자열을 또 json_payload로 감싸면 이중 인코딩됩니다.

**② 추가과제 stub을 `week05_tools()`에 남길지 → 이번 패스에서는 빼는 것을 권장.**
`create_shared_schedule`/`delete_shared_schedule`를 이번에 구현하지 않으면, Week 4에서 멘토가 지적한 "미완성 stub이 tool 목록에 노출돼 LLM이 호출할 수 있는" 문제가 그대로 재발합니다. 메인과제만 제출한다면 `week05_tools()`에서 이 두 tool을 빼는 게 안전합니다. (추가과제까지 할 계획이면 그대로 두고 다음 패스에서 구현.) — **이 결정은 사용자 확인 후 진행.**

**③ `collect_member_schedules`의 "나" 표기 → member_name="나"로 통일.**
`fixed/external_people_store.py`의 `PERSONAL_SHARED_MEMBER_NAME = "나"`와 맞춰, 내 일정 row의 member_name을 "나"로 넣어 외부 멤버 row와 같은 구조를 유지합니다.

## 단계별 계획 (Karpathy 가이드라인 형식)

```
1. 조회 wrapper 4개(search_previous_conversations / load_conversation_messages /
   extract_schedules_from_history / list_shared_schedules) 구현
   → verify: MCP subprocess가 뜨는 실호출이므로, 각 tool을 직접 호출해 반환 문자열/JSON이
     에러 없이 나오고 계약 필드(rows 등)가 있는지 확인

2. _personal_schedules_for_current_scope 구현
   → verify: 현재 대화 scope의 임시 일정 + SQLite 저장 일정이 중복 없이 합쳐지는지
     (같은 일정이 두 번 안 나오는지)

3. _collect_member_schedules + collect_member_schedules 구현
   → verify: 반환 rows에 "나"와 외부 멤버가 같은 필드 구조로 들어가고 schedule_summary가
     비어 있지 않은지

4. week05_prompt_parts() 채우기
   → verify: week05_system_prompt()가 에러 없이 생성되고, 새 tool 이름들이 프롬프트 본문에
     실제 언급되는지 (checks/tool_inventory.py에 week5를 추가하면 자동 확인 가능)

5. 전체 모듈 import 확인
   → verify: python -c "import student_parts.week05_load_kanas_past_conversations" 예외 없이 종료
```

## 검증 방식 비고

- MCP 조회는 실제 외부 SQLite(`data/kanana_external_people.sqlite3`)에 대한 **읽기 전용**이라 실호출로 검증해도 부작용이 없습니다(seed 데이터: 철수/영희/민준/서연/지훈/하린의 7월 일정).
- 추가과제 create/delete는 **쓰기**라 실호출 시 외부 공유 저장소에 test row가 남습니다 — 이번 메인 패스에서는 다루지 않으므로 해당 없음.
- 이 저장소에는 자동 테스트 하네스가 없으므로(README 명시), 검증은 임시 스크립트로 함수를 직접 호출하는 방식으로 진행하고 스크립트는 검증 후 삭제합니다.
- 최종 trace 확인(`./run.sh --week5`)은 사용자가 직접 채팅으로 진행하는 걸 권장(검증 체크리스트는 `WEEK05_IMPLEMENTATION_PLAN.md` 4장 참고).
- Week 4에서 만든 `checks/tool_inventory.py`에 week5 매핑 한 줄을 추가하면, 스텁/회귀/prompt 언급 검사를 week5에도 그대로 적용할 수 있습니다(선택).
