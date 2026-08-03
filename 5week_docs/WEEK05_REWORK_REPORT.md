# Week 5 재작업 결과 보고 (멘토 1차 리뷰 반영)

멘토(junho85) 1차 수정 요청 + AFK 운영 멘토링(`WEEK05_MENTORING.md`)을 반영해, **1000 케이스를 먼저 만들고 통과할 때까지 구현**한 결과. 진행 순서: 테스트 계획(`WEEK05_TEST_PLAN_1000.md`) → 1000 케이스 → 구현/수정 → 재검증.

## 1. 한 일

| 항목 | 내용 |
| --- | --- |
| **[수정요청] 날짜 범위 버그** | `_collect_member_schedules`에서 내 일정도 `date_from`~`date_to`(inclusive)로 필터. 범위 밖·date 없는 내 일정은 rows에서 제외 |
| **[추가과제]** | `create_shared_schedule`/`delete_shared_schedule` 구현(MCP wrapper) + `week05_tools()` 복귀 + 프롬프트에 등록/삭제 지시문 |
| **[검증]** | 1000 결정론적 케이스 + real-MCP 계약(범위밖 재현방지 + create/delete round-trip) + tool_inventory + golden |

변경 범위: `student_parts/week05_load_kanas_past_conversations.py`, `checks/`, `5week_docs/`만. (`fixed/`·타 주차 미접촉 — 멘토 2-6)

## 2. 정량 결과 (임계값 모두 도달)

| 지표 | 하네스 | 임계값 | 결과 |
| --- | --- | --- | --- |
| 1000 속성 (날짜필터·병합 불변식) | `checks/week05_property_1000.py` | 100% | **1000/1000 (100%)** |
| real-MCP 계약 (범위밖·순서·create/delete) | `checks/week05_contract_check.py` | 전부 PASS | **21/21 PASS** |
| 정적 조립 | `checks/tool_inventory.py` | PASS | **week05 전부 PASS** (21 tool, 스텁 0) |
| tool-selection | `checks/week05_golden.py` | external ≥70%, control 오호출 0 | **external 83.3%, control 0** |

- 1000 케이스는 **구현 전엔 87/1000**(범위 밖 일정 누출) → 수정 후 1000/1000. 버그를 스펙이 정확히 잡음.
- create/delete round-trip: 고유 id로 생성→list 확인→삭제→사라짐, 테스트가 만든 row만 건드리고 정리(실제 외부 DB 오염 없음).

## 3. 멘토링 반영 체크 (`WEEK05_MENTORING.md` 대응)

- **2-3 테스트를 고쳐 통과 금지**: 1000 케이스는 스펙으로 먼저 고정, 실패 시 **코드만** 수정(테스트 불변). 임계값은 `WEEK05_TEST_PLAN_1000.md`에 박제.
- **2-4 기준=스펙(인자 무시하면?)**: `date_from`/`date_to`를 무시하면 깨지는 "인자-무시 트랩" 그룹(D)과 경계값(C)을 명시적으로 포함. 이번 버그가 정확히 이 유형이었음.
- **2-5 임계값=상한**: 통과 임계값(70%)과 **목표치(90%) 분리**. golden external 4건 미달은 아래 §4에 원인·판단 기록.
- **2-1 같은 에러 2회면 정지**: 반복 중 동일 실패 2회 발생 없었음(1000은 1회 수정으로 100%).
- **2-6 변경 범위 확인**: 위 범위표대로 `student_parts/`·`checks/`·`docs`만.
- **2-2 토큰/반복 비용**: 반복의 대부분을 무료 결정론적(1000)으로 처리, 유료 golden은 1회만 재실행.

## 4. golden 남은 4건 (통과했지만 기록 — 멘토 2-5)

- external 24건 중 20건 통과(83.3%), **실패 4건은 전부 "tool 미호출"**(다른 tool 오라우팅 0, control 오호출 0). 즉 라우팅 자체는 깨끗하고, 일부 외부질문에서 검색을 아예 안 하고 대화로만 답하는 케이스만 남음.
- 이는 4주차에서도 관측된 "프롬프트 지시문이 tool 선택을 좌우 + 모호할 때 미호출" 패턴과 동일 계열.
- 판단: 임계값은 통과했고 목표치(90%)와의 격차는 **비결정적(재실행 시 실패 프롬프트가 바뀜)**이라, 특정 프롬프트를 쫓기보다 라우팅 지시문을 더 단정형으로 다듬는 것을 다음 개선 레버로 남김(멘토 2-2 비용·2-5 상한 균형). 무리한 과튜닝은 하지 않음.

## 5. 재현

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_property_1000.py   # 1000 결정론적(무료)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_contract_check.py   # real-MCP 계약
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/tool_inventory.py          # 정적
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_golden.py           # LLM(비용)
```
생성된 1000 케이스 스냅샷: `checks/week05_cases_1000.jsonl`.
