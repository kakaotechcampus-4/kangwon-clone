# Week4 메인과제 확인 + Tier1 체크 도구 구현 — 진행 보고

`docs/WEEK04_IMPLEMENTATION_PLAN.md` / `docs/WEEK04_MAIN_TASK_EXECUTION_PLAN.md` / `docs/ASSIGNMENT_CHECK_DESIGN.md`를 실제로 적용한 결과 보고서입니다.

## 1. Tier 1 정적 조립 검사 — `checks/tool_inventory.py`

### 어떻게 만들었나

`docs/ASSIGNMENT_CHECK_DESIGN.md` 14-27번 줄 설계를 그대로 코드화했습니다.

- **스텁 탐지 (`_is_stub`)**: `@tool`이 감싼 객체(`StructuredTool`)에서 `.func`로 원본 함수를 꺼내고, `inspect.getsource()`로 소스를 얻은 뒤 `ast.parse()`로 문법 트리를 만듭니다. 함수 본문에서 docstring(있다면)을 제외한 나머지가 정확히 `...`(Ellipsis) 표현식 하나뿐이면 스텁으로 판정합니다.

- **회귀 탐지**: week01→02→03→04 순서로 `weekNN_tools()`를 하나씩 로드하면서, 이전 주차에서 스텁이 아니었던 tool 이름이 이번 주차에서 스텁으로 바뀌면 실패로 기록합니다. (Week 3에서 실제로 겪었던 `personal_create_schedule` 회귀가 이 케이스입니다)

- **이름 중복 검사**: 같은 tool 이름이 목록에 두 번 이상 있으면 실패.

- **prompt 언급 검사**: `weekNN_prompt_parts()`를 호출해 하나의 문자열로 합치고, 스텁이 아닌(=구현된) tool 이름이 그 문자열 안에 실제로 등장하는지 확인합니다. 등장하지 않으면 실패.

### 설계 문서 대비 생략한 부분

`ASSIGNMENT_CHECK_DESIGN.md` 20번 줄의 "가이드 주석에 적힌 구현 대상 함수 이름이 tool 목록에서 빠졌는지"는 구현하지 않았습니다. 이건 각 주차 파일 맨 위 한국어 주석(`# 메인과제 구현 대상` 등)에서 함수 이름을 정규식/파싱으로 뽑아내야 하는데, 주석 형식이 주차마다 자유 서술이라 안정적으로 파싱할 규칙을 세우기 어렵습니다. 억지로 만들면 오탐(false positive)이 잦은 깨지기 쉬운 체크가 될 것 같아 이번 범위에서는 뺐습니다 — 스텁 탐지 + 회귀 탐지 + 중복 검사 + prompt 언급 검사 4가지만으로도 실제 겪은 버그 유형은 다 잡힙니다.

### 실행 방법

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/tool_inventory.py
```

Windows 콘솔 기본 인코딩이 한글 출력과 안 맞아서 깨져 보이는 문제가 있어(mojibake), `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` 환경변수를 붙여야 정상적으로 읽힙니다.

### 실행 결과

**1차 실행 (week04_prompt_parts에 제가 작성한 지시문이 있던 상태)**

```
FAIL  week04: 구현된 tool인데 system prompt에 이름이 언급되지 않음 = ['add_personal_reference']
```

제가 작성했던 프롬프트가 `search_personal_references`/`search_saved_requests`는 언급했지만, 참고자료를 **추가**하는 tool인 `add_personal_reference`는 이름 언급을 빠뜨렸다는 걸 실제로 잡아냈습니다. 도구가 의도한 대로 동작함을 확인한 사례입니다.

**2차 실행 (요청에 따라 `week04_prompt_parts()`를 TODO로 되돌린 뒤)**

```
FAIL  week04: 구현된 tool인데 system prompt에 이름이 언급되지 않음 =
  ['add_personal_reference', 'search_personal_references', 'search_saved_requests']
```

프롬프트가 비어 있으니 구현된 tool 3개 전부가 "언급 없음"으로 잡히는 게 **의도된 정상 상태**입니다. 프롬프트를 직접 작성해 넣으신 뒤 다시 이 스크립트를 돌리면, 세 이름이 문자열 안에 다 들어갔는지 이 도구가 그대로 확인해줍니다.

Week 1~3은 전부 통과(`PASS`)했고, Week 3에서 시도했던 회귀도 지금 코드에는 없다는 게 재확인됐습니다.

## 2. Week 4 메인과제 구현 현황

`docs/WEEK04_MAIN_TASK_EXECUTION_PLAN.md` 7-13번 줄이 정의한 범위 기준입니다.

| 항목 | 계획 문서상 원래 스텁 위치 | 실제 구현 후 현재 위치 | 상태 |
| --- | --- | --- | --- |
| `add_personal_reference_dict` | EXECUTION_PLAN.md 9번 줄 (219-229) | `week04_retrieve_nanas_memory.py:219` | 완료 |
| `search_personal_reference_hits` | EXECUTION_PLAN.md 10번 줄 (232-241) | `week04_retrieve_nanas_memory.py:231` | 완료 |
| `search_saved_request_rows` | EXECUTION_PLAN.md 11번 줄 (244-253) | `week04_retrieve_nanas_memory.py:254` | 완료 |
| `add_personal_reference`/`search_personal_references`/`search_saved_requests` tool 본문 | EXECUTION_PLAN.md 12번 줄 (283-304) | `week04_retrieve_nanas_memory.py:293,301,309` | 완료 |
| `week04_prompt_parts()` | EXECUTION_PLAN.md 13번 줄 (350-356) / IMPLEMENTATION_PLAN.md 92-103번 줄(2-4절) | `week04_retrieve_nanas_memory.py:359` | **의도적으로 TODO 상태로 되돌림 — 사용자 작성 예정** |

구현 세부 내용(어떤 코드를 썼는지)은 `docs/WEEK04_MAIN_TASK_EXECUTION_PLAN.md`의 단계별 계획(30-51번 줄)과 `docs/WEEK04_IMPLEMENTATION_PLAN.md`의 2-1~2-3절(30-90번 줄)에 있는 스케치와 동일하게 반영했고, 확정한 설계 결정 3가지(`ok`/`tool_name` 키 미포함, `tags` 리스트 round-trip, `safe_limit()` 가이드대로 유지)도 그대로 적용돼 있습니다 — `docs/WEEK04_MAIN_TASK_EXECUTION_PLAN.md` 21-28번 줄 참고.

`week04_prompt_parts()`만 이번 요청에 따라 원래의 `# TODO: Week 4 Nana memory agent system prompt를 자유롭게 추가하세요.` 주석 상태로 되돌렸습니다. 프롬프트에 꼭 담아야 할 내용(취향/메모 질문 vs 저장기록 질문 구분, `add_personal_reference` 사용 시점 등)은 `docs/WEEK04_IMPLEMENTATION_PLAN.md` 96-101번 줄에 정리돼 있으니 작성하실 때 참고하시면 됩니다.

## 3. 다음에 할 수 있는 것

- 직접 `week04_prompt_parts()` 작성 후 `checks/tool_inventory.py` 재실행 → `FAIL` 사라지는지 확인
- 추가과제(`search_conversation_messages` 계열)는 아직 미착수 상태
- Tier 2(실제 agent 호출 골든 케이스)는 `docs/ASSIGNMENT_CHECK_DESIGN.md`에 설계만 있고 미구현
