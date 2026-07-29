# 요약 (원본: WEEK05_IMPLEMENTATION_PLAN.md / WEEK05_MAIN_TASK_EXECUTION_PLAN.md)

키워드 압축본. 세부 근거/코드/줄번호는 각 원본 문서 참고. (docs/SUMMARY.md와 같은 구성)

---

# 1. WEEK05_IMPLEMENTATION_PLAN.md 요약

## 0. 핵심
- Week4=내 것(앱 내부) / **Week5=남의 것(외부 데이터를 MCP로 감싸기)**
- 학생은 SQL 안 짬. 실제 조회는 MCP 서버·store에 이미 있음 → **MCP tool 호출 + 결과를 agent JSON으로 전달하는 wrapper**만 구현
- 출처 3곳: 외부 멤버 대화·일정(ExternalPeopleSQLiteStore + mcp_server, MCP 호출) / 공유 일정 저장소(external_schedules, MCP 호출) / 내 일정(AppSQLiteStore.list_schedules + PERSONAL_SCHEDULES, 직접 읽기)
- 할일 = ① MCP tool 올바르게 호출 + ② 결과 그대로(또는 json_payload) 반환. 단 collect_member_schedules만 "합치기" 로직

## 1. MCP 호출 두 갈래 (⚠ 가장 중요)
- `call_mcp_tool_sync(name, args)` → **str** → 그대로 return (search_previous / extract_schedules / list_shared / create / delete)
- `call_external_tool_payload(name, args)` → **dict** → json_payload로 감싸 return (**load_conversation_messages 하나만**)
- 함정: str을 또 json_payload로 감싸면 이중 인코딩. 반환 타입 혼동 금지
- MCP 서버는 매 호출마다 stdio subprocess로 뜸(느리지만 수업 규모엔 무해)

## 2. 구현 순서
1. search_previous_conversations (str pass-through)
2. load_conversation_messages (payload→json_payload, 유일 예외)
3. extract_schedules_from_history (str pass-through)
4. list_shared_schedules (str pass-through)
5. _personal_schedules_for_current_scope → _collect_member_schedules → collect_member_schedules (유일 합치기)
6. week05_prompt_parts() 지시문 (메인, 함수만큼 중요)
7. create/delete_shared_schedule (추가과제)

## 3. 단계별 스케치
- **search_previous**: `call_mcp_tool_sync("search_previous_conversations", {query,member_names,limit})` 그대로 return. 멤버이름 정규화 중복 X
- **load_conversation**: `call_external_tool_payload("load_conversation_messages", {conversation_id})` → json_payload. sender/content/created_at 순서 보존(가공 X)
- **extract_schedules**: `call_mcp_tool_sync("extract_schedules_from_history", {member_names,date_from,date_to})`. rows에 member_name/title/date/start_time/end_time/notes 유지
- **list_shared**: `call_mcp_tool_sync("list_shared_schedules", {...5개 인자})`. 필터 없으면 기본 실습 일정 반환. Week6 재사용
- **collect_member_schedules 계열**(유일 합치기):
  - `_personal_schedules_for_current_scope()`: SQLite list_schedules + PERSONAL_SCHEDULES 중 현재 scope만, id 기준 중복 제거
  - `_collect_member_schedules()`: 내 일정→member_name="나"(_structured_request_from_schedule_row), 외부→함수 안에서 extract_schedules_from_history 호출+json.loads, normalize helper로 이름/날짜 정규화, external_schedule_summary로 schedule_summary
  - tool: 위 감싸 `{rows, schedule_summary}` json_payload
- **week05_prompt_parts()**: 개인 저장/RAG=이전 주차 tool / 외부 멤버 대화·일정=MCP wrapper / 수집=collect_member_schedules / "최종 회의시간 선택"은 Week6 범위
- **create/delete_shared(추가)**: `call_mcp_tool_sync(...)` 그대로. schedule_id/source_conversation_id 보존. 안 하면 week05_tools()에서 빼기

## 4. 검증
- run.sh --week5, trace에서 tool 호출 순서 확인
- collect_member_schedules rows에 "나"+외부 멤버 같은 구조 / list_shared에 rows+schedule_summary 유지

## 5. 흔한 실수
- 반환 타입 혼동(load만 dict→json_payload, 나머지 str→그대로)
- 중복 정규화(멤버이름/날짜는 MCP 경계서 이미 처리)
- collect_member: PERSONAL_SCHEDULES 전체 합치면 다른 scope/이미 저장된 것 중복 → scope 필터+중복 제거
- load_conversation 메시지 순서 가공 금지
- week05_prompt_parts() 미작성(Week4 동일 함정)
- 추가과제 stub을 week05_tools()에 남기면 Week4 멘토 지적(미완성 stub 노출) 재발

---

# 2. WEEK05_MAIN_TASK_EXECUTION_PLAN.md 요약

## 범위: week05 파일 8곳 (helper 2 + tool 5 + prompt 1)
- _personal_schedules_for_current_scope / _collect_member_schedules
- search_previous_conversations / load_conversation_messages / extract_schedules_from_history / list_shared_schedules / collect_member_schedules
- week05_prompt_parts()
- fixed/·mcp_server/·타주차 = 손 안댐. 추가과제 2개는 스텁 유지

## 구현전 결정 3가지
- ① 반환 처리: load만 dict→json_payload, 나머지 str 그대로 (이중 인코딩 방지)
- ② 추가과제 stub → 이번 패스에선 week05_tools()에서 **빼기 권장**(Week4 stub 노출 문제 재발 방지) — **사용자 확인 후**
- ③ 내 일정 member_name="나"(PERSONAL_SHARED_MEMBER_NAME과 일치)

## 단계별계획 (Karpathy)
1. 조회 wrapper 4개 → verify: 실호출로 반환/계약 필드 확인(MCP 읽기전용이라 안전)
2. _personal_schedules_for_current_scope → verify: 현재 scope 임시+SQLite 중복 없이 합쳐지는지
3. _collect + collect_member_schedules → verify: rows에 "나"+외부 같은 구조, schedule_summary 비지 않음
4. week05_prompt_parts() → verify: system_prompt 생성 + 새 tool 이름 프롬프트 언급
5. import 확인

## 검증 비고
- MCP 조회는 외부 SQLite 읽기전용이라 실호출 무해(seed: 철수/영희/민준/서연/지훈/하린 7월 일정)
- 추가과제 create/delete는 쓰기라 이번 범위 밖
- 자동 테스트 없음 → 임시 스크립트 직접호출 검증 후 삭제
- checks/tool_inventory.py에 week5 매핑 추가하면 스텁/회귀/prompt 검사 재사용 가능(선택)
