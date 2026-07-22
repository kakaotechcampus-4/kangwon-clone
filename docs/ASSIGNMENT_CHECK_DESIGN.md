# 과제 구현 확인용 체크 도구 — 설계 문서

이 문서는 설계만 다룹니다. 코드는 아직 작성하지 않았습니다.

## 왜 필요한가

이 저장소에는 자동 테스트 하네스가 없어서(README 명시), 지금까지는 앱을 직접 켜서 "상세" 탭의 trace JSON을 눈으로 읽는 방식으로만 검증해왔습니다. 그런데 지금까지 겪은 실제 버그 두 건을 보면 성격이 다른 두 종류입니다.

1. **조립(assembly) 회귀** — Week 3에서 `week03_tools()`가 아직 스텁인 `personal_create_schedule`로 Week 1의 멀쩡한 tool을 무조건 바꿔치기했던 문제. 이건 **LLM을 한 번도 안 부르고, 파이썬 코드만 봐도 알 수 있는 버그**입니다.
2. **의도 전달 실패** — 함수는 다 구현했는데 system prompt에 그 tool을 언제 쓰라는 지시가 빠져서 LLM이 아예 그 tool을 안 고르는 문제(3주차 리뷰에서 "서술문 vs 지시문" 이슈, 이번 4주차 문서에서도 미리 짚었던 부분). 이건 **실제로 LLM을 불러서 어떤 tool을 고르는지 봐야만** 알 수 있습니다.

한 가지 도구로 이 둘을 다 잡으려 하면 어설퍼지므로, **정적 검사(무료·즉시)** 와 **동적 검사(실제 LLM 호출·비용 발생)** 두 단계로 나눠서 설계합니다.

## Tier 1 — 정적 조립 검사 (무료, API 호출 없음)

### 무엇을 검사하나

- **스텁 탐지**: `weekNN_tools()`가 반환하는 각 tool의 원본 함수 바디가 `...`(Ellipsis) 하나뿐인지 검사. 파이썬 함수 소스를 `ast`로 파싱해서 "docstring 다음 statement가 `Expr(value=Constant(value=Ellipsis))` 하나뿐인가"를 판별합니다. `@tool` 데코레이터가 감싼 객체(`StructuredTool`)에서는 `.func` 속성으로 원본 함수를 꺼냅니다.
- **주차 간 tool 목록 회귀 탐지**: `weekN_tools()`와 `week(N-1)_tools()`를 비교해서, 이전 주차엔 있던 이름의 tool이 이번 주차에서 **스텁으로 바뀌었는지** 확인합니다. (이번에 실제로 겪은 회귀가 정확히 이 케이스입니다 — 이름은 같은데 구현이 스텁으로 퇴화)
- **이름 중복/누락**: 같은 tool 이름이 목록에 두 번 있거나, 가이드 주석에 적힌 "구현 대상" 함수 이름이 실제 tool 목록에서 빠졌는지.
- **prompt 조립 확인**: `weekNN_prompt_parts()`가 예외 없이 문자열 리스트를 만드는지, 그리고 그 주차에 새로 구현된(스텁이 아닌) tool 이름이 최종 system prompt 문자열 안에 실제로 등장하는지(문자열 포함 여부) — "구현은 했는데 prompt에서 언급이 없는" 케이스를 잡기 위함입니다.

### 왜 이 방식이 안전한가

- LLM을 전혀 안 부르므로 API 키가 없어도, 비용이 없어도, 몇 초 안에 실행됩니다.
- import만으로 검사가 끝나므로 실제 SQLite/ChromaDB 데이터에 어떤 부작용도 남기지 않습니다.
- 코드를 수정할 때마다(커밋 전, PR 올리기 전) 매번 돌려도 부담이 없습니다.

## Tier 2 — 실제 agent 호출 기반 trace 검사 (API 비용 발생)

### 무엇을 검사하나

"케이스" 하나는 다음 4가지로 정의합니다.

```python
{
    "week": 4,
    "prompt": "아침에 집중 잘 되는 시간 있으면 참고자료에서 찾아줘",
    "expect_tool_calls": ["search_personal_references"],
    "expect_json_keys": {"search_personal_references": ["hits"]},
}
```

실행 절차:
1. 해당 주차의 `build_week_agent()`로 실제 agent를 만듭니다.
2. `agent.invoke({"messages": [{"role": "user", "content": prompt}]})`로 실제 LLM을 호출합니다.
3. 결과를 `fixed/langchain_trace.py::extract_agent_events(result)`에 넣습니다 — 이 함수는 이미 앱이 쓰는 것과 동일한 코드로, `tool_call`/`tool_result` 이벤트 리스트를 뽑아줍니다([fixed/langchain_trace.py:114-145](fixed/langchain_trace.py#L114-L145)).
4. 검증:
   - `expect_tool_calls`의 모든 이름이 실제 `tool_call` 이벤트에 등장했는지
   - 각 tool의 `tool_result` 이벤트 `content`(이미 JSON 파싱되어 있음)가 `expect_json_keys`에 정의된 top-level 키를 갖고 있는지

이건 "골든 케이스" 방식이고, 멘토님이 리뷰에서 언급했던 `golden_cases.py`/`run_golden.py` 인프라와 같은 개념입니다(현재 이 저장소엔 실제로 존재하지 않는 걸 확인했으나, 같은 이름/개념으로 직접 만드는 것을 제안합니다).

### 주의해야 할 부작용 — 실제 데이터에 쓰는 tool

Tier 2는 실제 `build_week_agent()`를 쓰므로, 케이스의 프롬프트가 "일정 저장해줘"/"참고자료 추가해줘" 같은 **쓰기 tool**을 유도하면 학생의 실제 `data/kanana_app.sqlite3`, `data/chroma`에 테스트 데이터가 남습니다. 두 가지 대응 옵션이 있습니다.

| 옵션 | 설명 | 트레이드오프 |
| --- | --- | --- |
| A. 쓰기 케이스 제외 | 검색/조회 tool만 골든 케이스로 다룬다 | 안전하지만 `save_structured_request`/`add_personal_reference` 같은 쓰기 tool의 실제 LLM 선택 여부는 못 검증 |
| B. 격리된 DB/Chroma 경로로 실행 | `CONFIG.app_db_path`/`CONFIG.chroma_dir` 대신 테스트 전용 임시 경로를 가리키는 별도 store로 agent를 만든다 | 쓰기 tool도 검증 가능하지만, `build_week_agent()`가 모듈 전역 `SQLITE_STORE`/`REFERENCE_STORE`를 참조하는 구조라 완전한 격리에는 약간의 monkeypatch가 필요 |

**추천: A로 시작.** 지난 3주차 회귀도, 4주차에서 미리 짚은 우려도 전부 "조회/tool 선택" 문제였지 "쓰기 데이터 오염" 문제가 아니었습니다. 쓰기 tool 골든 케이스는 필요성이 커지면 B로 확장하는 걸 권장합니다.

### 비용 성격

케이스 1개당 LLM 호출 1회(+ ChromaDB 검색 tool이 선택되면 임베딩 API 호출 추가)가 발생합니다. Tier 1과 달리 **매 저장마다 자동 실행할 성격이 아니고, PR 올리기 전 한 번씩 수동 실행하는 용도**로 설계합니다.

## 파일 배치안

```
checks/
  tool_inventory.py     # Tier 1: 스텁/회귀/이름 검사 로직 + CLI
  golden_cases.py        # Tier 2: 주차별 케이스 목록 (dict 리스트)
  run_golden.py          # Tier 2: 케이스 실행기
```

- `checks/`는 `student_parts/`, `fixed/`와 분리된 새 최상위 폴더로 둡니다 — 학생 구현 코드(`student_parts/`)도, 강사 기준 코드(`fixed/`)도 아닌 "검증 전용" 코드라는 걸 위치로 명확히 하기 위함입니다.
- `run.sh`는 건드리지 않습니다(앱 실행 스크립트와 검증 스크립트는 다른 진입점).

## 실행 방법 (제안)

```bash
uv run python checks/tool_inventory.py           # Tier 1만 — 기본, 무료, 항상 실행 가능
uv run python checks/run_golden.py --week 4      # Tier 2 — 지정 주차만, API 비용 발생
uv run python checks/run_golden.py               # Tier 2 — 전체 주차
```

## 출력 형식

기존에 만들었던 임시 검증 스크립트들과 같은 스타일로, `PASS`/`FAIL` 한 줄씩 찍고 마지막에 요약(`N개 실패` 또는 `ALL CHECKS PASSED`)과 함께 실패 시 exit code 1을 반환합니다. 별도 로그 파일 저장은 기본으로 두지 않고 콘솔 출력만으로 시작하되, 필요해지면 `checks/logs/`(`.gitignore` 대상)에 실행 시각별 JSON 리포트를 추가하는 걸 다음 단계로 남겨둡니다.

## 구현 전 확인하고 싶은 것

1. **범위**: Tier 1(정적, 무료)만 먼저 만들까요, 아니면 Tier 1+2를 한 번에 만들까요? Tier 2는 실제 API 호출 비용이 든다는 점이 다릅니다.
2. **Tier 2 케이스 대상**: 우선은 위 "옵션 A"(조회/검색 tool 중심, 쓰기 tool 제외)로 시작하는 데 동의하시나요?
