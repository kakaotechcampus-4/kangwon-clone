# Week 5 재작업 테스트 계획 — 1000 케이스 (구현 전 정의)

멘토 1차 리뷰(PR #135, `WEEK05_MENTORING.md`)를 반영해, **구현 전에 1000개 테스트 케이스를 먼저 정의**한다. 이 문서는 그 설계이고, 실제 1000개는 `checks/week05_property_1000.py`가 결정론적으로 생성한다(재현 가능). 생성된 케이스 스냅샷은 `checks/week05_cases_1000.jsonl`로 덤프한다.

## 0. 설계 원칙 (멘토링 반영)

- **2-4 "기준=스펙, 인자마다 무시하면?"**: `collect_member_schedules`는 `member_names`/`date_from`/`date_to`를 받는다. 각 인자를 무시하면 깨지는 케이스를 명시적으로 만든다. 특히 **날짜 범위 밖 내 일정이 rows에 섞이는** 이번 버그를 스펙으로 못박는다.
- **2-3 "테스트를 고쳐 통과시키지 말 것"**: 이 케이스들은 스펙이다. 구현이 통과 못 하면 **코드를 고치지 테스트를 느슨하게 하지 않는다**. 임계값은 이 문서에 고정한다(= 나중에 대조 가능).
- **2-5 "임계값=상한 주의"**: 결정론적 계약/속성 케이스는 **100%(하드 게이트)**. golden(LLM)은 통과 임계값과 목표치를 분리하고, 통과 후에도 실패 케이스를 눈으로 본다.
- **2-1 "같은 에러 2회면 정지·기록"**: 반복 수정 중 동일 실패가 2회 반복되면 멈추고 기록한다.
- **2-6 "변경 범위 확인"**: `student_parts/week05_*.py`와 `checks/`만 수정한다.

## 1. 1000 케이스 구성 (결정론적, LLM 불필요)

`_collect_member_schedules`의 **날짜 범위 필터 + 병합 불변식**을 대량 속성 검증한다. 외부 MCP 경계는 이 유닛 테스트에서 **주입(monkeypatch)** 으로 대체해 subprocess 없이 빠르게 1000회 돌린다. (실제 MCP 통합은 §3의 real-MCP 계약 검사가 별도로 담당.)

| 그룹 | 개수 | 무엇을 검증 | 통과 조건 |
| --- | --- | --- | --- |
| A. 날짜범위 필터 그리드 | 40 날짜 × 20 범위 = **800** | 내 일정 1건을 date D에 두고 범위 [F,T]로 조회 | D가 [F,T] 안 ⇔ 내 일정이 rows에 존재. **범위 밖이면 rows에 없어야** |
| B. 다건 혼합 | **120** | 여러 내 일정(범위 안/밖 섞음) + 외부 mock rows | rows의 모든 항목 date가 [F,T] 안, 범위 안 내 일정만 포함, 외부 rows 보존 |
| C. 경계값 | **40** | D == F, D == T(경계 포함), D = F-1일, D = T+1일 | 경계는 포함(inclusive), 경계±1일은 규칙대로 |
| D. 인자-무시 트랩 | **40** | date_from만/ date_to만/ 둘 다 무시하면 실패하도록 설계 | 셋 다 존중해야 통과 |

합계 = 1000. 모든 케이스 공통 불변식:
- 모든 row는 `{member_name,title,date,start_time,end_time,notes}` 6키를 가진다.
- 내 일정 row의 member_name은 `"나"`.
- 외부 mock rows는 그대로 보존된다(내 일정 필터가 외부를 건드리지 않음).
- **결과 rows에 `date_from`~`date_to`(inclusive) 밖 date가 하나도 없어야 한다.** ← 리뷰 핵심 계약.

날짜 없는(None) 내 일정은 범위 안에 놓을 수 없으므로 제외한다(외부 일정은 항상 date가 있음과 동일 기준).

## 2. 임계값 (고정)

- **결정론적 1000 케이스: 1000/1000 통과 (100%) — 하드 게이트.** 하나라도 실패면 코드 수정.
- **real-MCP 계약 검사(§3): 전 항목 PASS.**
- **tool_inventory(week5): PASS** (추가과제 tool 복귀 시 프롬프트 언급 포함).
- **golden(LLM) tool-selection**: 통과 임계값 external ≥ 70%, control 오호출 0. **목표치는 90%로 별도** — 통과해도 실패 케이스는 눈으로 확인해 원인 기록(멘토 2-5).

## 3. real-MCP 계약 검사 추가분 (`checks/week05_contract_check.py`)

1000 유닛과 별개로, 실제 MCP를 쓰는 통합 계약을 보강한다.
- **(신규) 날짜 범위 버그 재현 방지**: 현재 대화에 8월 일정을 seed + 외부 철수(7월)로 `collect_member_schedules(date_from=7/7,date_to=7/16)` → rows에 8월 일정이 **없어야** 한다.
- (기존) 5개 조회 tool 계약 + 순서 보존 + 병합 구조.
- **(추가과제) create/delete round-trip**: 고유 schedule_id로 `create_shared_schedule` → `list_shared_schedules`에 나타남 → `delete_shared_schedule` → 사라짐. 테스트가 만든 row만 건드리고 정리(실제 외부 DB 오염 없음).

## 4. 이번에 함께 하는 구현

- **[수정 요청]** `_collect_member_schedules`: 내 일정 row 생성 시 date가 [date_from,date_to] 밖이면 skip.
- **[추가과제]** `create_shared_schedule`/`delete_shared_schedule` 구현 + `week05_tools()` 복귀 + `week05_prompt_parts()`에 등록/삭제 지시문(그래야 tool_inventory 프롬프트 언급 통과, Week4 교훈).

## 5. 실행

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_property_1000.py   # 1000 결정론적(무료)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_contract_check.py   # real-MCP 계약
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/tool_inventory.py          # 정적
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_golden.py           # LLM(비용)
```
