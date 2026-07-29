# Week 5 메인·공통과제 구현 + 정량 검증 보고서

AFK 자율 작업으로 Week 5 **메인 + 공통과제**를 구현하고, "평가지표·테스트 케이스를 먼저 만들고 임계값 도달까지 반복"하는 방식으로 검증한 결과입니다. (추가과제 create/delete_shared_schedule는 범위 밖 — 스텁으로 두되 `week05_tools()`에서 제거해 노출 안 함.)

## 1. 구현 범위

| 대상 | 위치 | 상태 |
| --- | --- | --- |
| `_personal_schedules_for_current_scope` (helper) | week05...py:189 | 구현 |
| `_collect_member_schedules` (helper) | :276 | 구현 |
| `search_previous_conversations` (tool) | :289 | 구현 (str pass-through) |
| `load_conversation_messages` (tool) | :301 | 구현 (payload→json_payload) |
| `extract_schedules_from_history` (tool) | :309 | 구현 (str pass-through) |
| `list_shared_schedules` (tool) | :345 | 구현 (str pass-through) |
| `collect_member_schedules` (tool) | :359 | 구현 (병합 로직) |
| `week05_prompt_parts()` | :388 | 구현 (라우팅 지시문) |
| `week05_tools()` | | 추가과제 2개 제거 |
| create/delete_shared_schedule (추가) | :317, :334 | **스텁 유지, 목록서 제외** |

**핵심 설계**: 조회 wrapper 4개는 `call_mcp_tool_sync`(문자열)를 그대로 반환, `load_conversation_messages`만 `call_external_tool_payload`(dict)→`json_payload`. `collect_member_schedules`만 내 일정("나")과 외부 멤버 일정을 같은 `member_name/title/date/start_time/end_time/notes` 구조로 병합 + `schedule_summary` 반환. 멤버명/날짜는 `normalize_external_*` helper로 정규화(collect 한정), wrapper에선 중복 정규화 안 함.

## 2. 정량 평가지표 & 임계값 (구현 전 정의)

구현에 앞서 `checks/`에 테스트 하네스를 먼저 작성한 뒤, 그 지표를 넘길 때까지 구현·수정하는 방식으로 진행:

| 지표 | 하네스 | 성격 | 임계값 |
| --- | --- | --- | --- |
| M1 계약 정확성 | `checks/week05_contract_check.py` | 결정론적, 실제 MCP read-only | **100%** (하드 게이트) |
| M2 정적 조립 | `checks/tool_inventory.py` (week5 추가) | 스텁/회귀/이름/prompt 언급 | **전부 PASS** |
| M3 tool-selection | `checks/week05_golden.py` | 실제 agent, LLM | **external ≥70% AND control 오호출 0** |

## 3. 검증 결과 (전부 임계값 도달, 반복 0회 — 첫 구현에서 통과)

### M1 계약 정확성 — 15/15 PASS (100%)
- 5개 tool 전부 MCP 호출 → 계약 필드 반환 확인 (rows / schedule_summary 등)
- `load_conversation_messages`: created_at 오름차순(메시지 순서 보존) 확인
- `collect_member_schedules`: "나"(임시 일정 seed) + 외부 멤버(철수)가 **같은 구조 rows로 병합**, schedule_summary 비어있지 않음 확인
- `_personal_schedules_for_current_scope`: 현재 scope 임시 일정 포함 / 다른 scope 제외(중복·범위 필터) 확인

### M2 정적 조립 — week5 전부 PASS
- 스텁 tool 없음(추가과제 2개는 `week05_tools()`에서 제거됨) / 이름 중복 없음 / 이전 주차 대비 회귀 없음 / 구현된 5개 tool 전부 system prompt에 언급됨

### M3 tool-selection (golden 40케이스) — 임계값 통과
| 카테고리 | 결과 |
| --- | --- |
| external_people (외부 tool 호출돼야) | **20/24 = 83.3%** (≥70% ✅) |
| control (외부 tool 오호출 없어야) | **오호출 0/16건** (✅) |
- external 실패 4건은 전부 "tool 미호출"(다른 tool로 오라우팅 0). 임계값 내라 추가 튜닝 불필요.

## 4. 재현 방법

```bash
# M1 계약 정확성 (실제 MCP, read-only, 무료·결정론적)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_contract_check.py

# M2 정적 조립 (무료)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/tool_inventory.py

# M3 tool-selection (실제 LLM, API 비용 발생, 데이터 임시복사 격리)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_golden.py
```

## 5. 비고

- **MCP subprocess**: `fixed/mcp_client.py`가 매 호출마다 `mcp_server/sqlite_mcp_server.py`를 stdio subprocess로 띄우는 구조가 이 환경에서 정상 동작함을 스모크 테스트로 먼저 확인 후 진행.
- **데이터 무결성**: M1은 외부 SQLite read-only + "나" 일정은 인메모리 `PERSONAL_SCHEDULES`로만 seed(DB 미변경). M3은 실제 data/를 임시 폴더로 복사·격리. 실제 data/ 변경 없음.
- **추가과제(create/delete_shared_schedule)**: 이번 범위 밖. 스텁으로 두되 `week05_tools()`에서 빼서 Week 4에서 멘토가 지적한 "미완성 stub 노출" 문제를 원천 차단.
- **미세 개선 여지**: golden external 4건 미호출 — 더 끌어올리려면 프롬프트 라우팅을 더 단정형으로 할 수 있으나, Week 4에서 확인한 시소/과튜닝 리스크가 있어 임계값 도달 시점(83.3%)에서 중단.
