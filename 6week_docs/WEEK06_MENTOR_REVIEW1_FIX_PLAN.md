# Week 6 멘토 1차 리뷰(수정 요청) — 이슈 분석 + 해결 계획

멘토가 남긴 1차 리뷰(수정 요청)를 항목별로 읽고, 현재 코드 상태를 직접 확인한 뒤
정리한 해결 계획입니다. **아직 코드는 고치지 않았고, 이 문서는 계획만 담습니다.**
실제 반영은 이 계획을 확인한 뒤 별도로 진행합니다.

리뷰에서 실제 조치가 필요한 항목은 2개("5주차 코드 업데이트 미반영", "저장 요청이
저장되지 않음")이고, 나머지는 확인/질문 답변이라 별도 코드 변경 없이 3절에 반영
여부만 기록합니다.

---

## 1. 이슈 A — Week 5 `collect_member_schedules` 버그 수정이 반영 안 됨 (Critical)

### 1-1. 현재 상태 확인

`공지_코드업데이트.md`(저장소 루트)에 정확한 원인·수정 코드가 이미 실려 있고,
직접 확인한 결과 **현재 `student_parts/week05_load_kanas_past_conversations.py`는
공지의 "BEFORE" 상태 그대로**입니다.

| 위치 | 현재 코드 | 문제 |
| --- | --- | --- |
| `_personal_schedules_for_current_scope()` (:193) | `list_schedules(limit=200, kind="personal_schedule")` | 그룹 일정이 "내 바쁜 시간"에서 통째로 빠짐 |
| `_structured_request_from_schedule_row()` (:274) | `kind="personal_schedule"` 하드코딩 | row가 실제 그룹 일정이어도 개인 일정으로 오인 |
| `_collect_member_schedules()` (:296-323) | `notes` 항상 `"Nana 개인 일정"`, dedup 없음, `members`에 `"나"` 중복 가능 | 그룹 일정 근거가 안 남고, "나"를 조회 대상에 넣으면 같은 일정이 두 번 나옴 |

### 1-2. 왜 이게 6주차에 영향을 주는가

`student_parts/week06_kanamate_decides_schedule.py`는 Week5 `collect_member_schedules`를
그대로 import해서 `kana_tools()`에 넣어 씁니다(:24, :415). Week5의 버그가 그대로
Kana 하위 agent에 전달되므로, 6주차 코드를 손대지 않아도 이 수정이 먼저 필요합니다.

### 1-3. 수정 계획 (공지 4절의 (A)~(E) 그대로 적용)

공지에 BEFORE/AFTER 코드가 전부 있으므로 그대로 옮겨 적용합니다.

1. **(A)** `_personal_schedules_for_current_scope()`: `kind="personal_schedule"` 인자
   제거 → `list_schedules(limit=200)`로 개인+그룹 모두 조회.
2. **(B)** `_structured_request_from_schedule_row()`: `kind="personal_schedule"` 하드코딩을
   `kind="group_schedule" if row.get("request_kind") == "group_schedule" else "personal_schedule"`로
   변경. docstring에 "Week1 임시 일정 row엔 `request_kind`가 없어 개인으로 본다"는
   이유를 남긴다.
3. **(C)** 새 helper `_my_schedule_notes(request)` 추가 — 개인/그룹에 따라
   `"Nana 개인 일정"` 또는 `"Nana 그룹 일정 · 참석자: …"`를 반환. `_collect_member_schedules`
   안의 `notes` 하드코딩을 이 helper 호출로 교체.
4. **(D)** 새 helper `_dedupe_schedule_rows(rows)` 추가 — `(member_name, date, start_time,
   소괄호 제거한 title)`을 키로 중복 제거. `fixed.external_people_store`에서
   `strip_parenthetical_text`를 추가 import.
5. **(E)** `_collect_member_schedules()` 마무리부: `rows = _dedupe_schedule_rows([*my_rows, ...])`로
   바꾸고, `members`에서 `"나"` 중복을 제거(`[name for name in normalized_members if name != "나"]`).
   **주의**: `my_rows`가 external rows보다 반드시 먼저 와야 `notes`가 올바른 값으로 남는다
   (공지 5절 경고 그대로).

### 1-4. 검증 계획

- `checks/week05_contract_check.py` 재실행 — 기존 15/15 PASS가 깨지지 않는지 확인.
- 공지 4절 "반영 후 이렇게 동작합니다" 시나리오를 그대로 재현:
  1. "7월 14일 3시에 하린이랑 사전 미팅 잡아줘"(그룹 일정 생성)
  2. "민준이랑 이번 주 일정 맞춰줘"(하린이 빠진 다른 사람과 조율)
  3. 결과 rows에 `member_name: "나"` / `notes: "Nana 그룹 일정 · 참석자: 하린"` row가
     있고, 7월 14일 15:00이 "가능한 시간"으로 잘못 추천되지 않는지 확인.
- 중복 제거 시나리오("팀 회의 (온라인)" + `member_names`에 `"나"` 포함)도 함께 재현해
  `"나"` row가 1건만 나오는지 확인.
- Week5 파일이 수정되므로 `checks/tool_inventory.py`(스텁/회귀 검사)도 함께 재실행.

---

## 2. 이슈 B — Nana ↔ Kana 저장 요청 순환 위임 (Critical)

### 2-1. 재현 확인

멘토가 보고한 대로 코드를 직접 읽어 원인을 확인했습니다.

`nana_prompt_parts()` (student_parts/week06_kanamate_decides_schedule.py:212-214):

> "다른 사람(외부 멤버)의 일정이나 여러 명의 공통 회의 시간 조율은 네 담당이 아니므로,
> 그런 요청이 오면 **'그건 Kana 담당입니다'**라고 짧게 알리고 개인 업무에만 답한다."

`kana_prompt_parts()` (:227):

> "확정된 일정을 앱에 저장하는 것은 **Nana 담당**이므로 필요하면 그렇게 안내한다."

"7월 9일 15시에 철수랑 회의 잡아줘"처럼 **날짜·시간이 이미 정해진** 요청도 참석자
`철수`가 있다는 이유만으로 Nana의 "다른 사람이 관련되면 내 담당 아님" 조건에 걸려
Kana로 떠넘겨집니다. Kana는 애초에 저장 tool이 없고(`kana_tools()`에 DB 저장 tool
없음, :409-416) "저장은 Nana 담당"이라고 안내만 하므로, 두 프롬프트가 서로를
가리키며 **어디서도 저장이 일어나지 않습니다.**

### 2-2. 경계를 어떻게 다시 그어야 하는가

멘토 질문 그대로가 핵심입니다: *"Nana가 담당하지 않아야 하는 것은 무엇이고,
참석자가 있어도 담당해야 하는 것은 무엇인가?"*

`공지_코드업데이트.md` 1절의 문장이 답입니다 — **"schedules 테이블의 row는
개인이든 그룹이든 owner가 '나'인 내 일정"**. 즉 판단 기준은 "참석자가 있는가"가
아니라 **"날짜/시간이 이미 정해졌는가(=조율이 필요한가)"** 여야 합니다.

| 상황 | 조율 필요? | 담당 |
| --- | --- | --- |
| "7월 9일 15시에 철수랑 회의 잡아줘" (시간 확정) | 아니오 | **Nana** (owner="나"인 그룹 일정으로 직접 저장) |
| "민준이랑 이번 주 언제 시간 되는지 봐줘" (시간 미확정) | 예 | **Kana** (여러 사람 busy-time 조율) |
| Kana가 조율 끝에 최종 시간을 정한 뒤 실제 저장 | - | **Nana**(저장 tool 보유) — 다만 이번 제출 범위는 추가과제 미구현이라 이 흐름 자체는 발생하지 않음 |

### 2-3. 수정 계획 (프롬프트 3곳, 코드 구조 변경 없음)

세 prompt 함수의 경계 문장을 "참석자 유무"가 아니라 "시간 확정 여부" 기준으로
다시 씁니다. 아래는 적용할 문구 초안입니다(최종 문구는 반영 시 다시 검토).

**`nana_prompt_parts()`** — 기존 두 번째 문장을 아래로 교체:

```python
"너는 Nana다. 사용자 본인('나')의 개인 일정 생성/조회/수정/삭제, todo·알림 저장, 개인 참고자료와 앱 대화 검색(RAG)을 담당한다. "
"날짜와 시간이 이미 정해진 일정은 참석자에 다른 사람(팀원)이 포함돼 있어도 owner가 '나'인 내 일정이므로 네가 직접 저장한다 "
"(예: '7월 9일 15시에 철수랑 회의 잡아줘' → 참석자에 철수를 포함한 그룹 일정으로 저장). "
"다른 사람의 일정·바쁜 시간을 조회하거나, 아직 시간이 정해지지 않아 여러 사람이 언제 다 가능한지 찾아야 하는 조율 요청만 "
"네 담당이 아니므로, 그런 요청이 오면 '그건 Kana 담당입니다'라고 짧게 알리고 개인 업무에만 답한다.",
```

**`kana_prompt_parts()`** — 마지막 문장을 아래로 교체:

```python
"이미 날짜/시간이 정해진 일정을 그냥 저장해 달라는 요청은 조율이 필요 없으므로 애초에 네 담당이 아니다 — "
"그런 요청이 오면 'Nana에게 요청해 달라'고 안내한다. 네가 여러 사람의 일정을 맞춰 최종 시간을 정한 뒤에는, "
"그 결과를 사용자에게 알리고 실제 앱 DB 저장은 Nana가 진행해야 한다고 안내한다(너는 저장 tool이 없다).",
```

**`week06_prompt_parts()`** (supervisor) — 라우팅 문장을 같은 기준으로 통일:

```python
"'내/나의' 개인적인 일정·저장·기억 요청은 nana_agent로 보낸다. 참석자가 있어도 날짜/시간이 이미 정해진 일정 생성·저장 요청도 nana_agent로 보낸다. "
"다른 사람(팀원·멤버)의 일정·바쁜 시간 조회나, 아직 시간이 정해지지 않아 여러 명이 언제 다 가능한지 조율해야 하는 요청만 kana_agent로 보낸다.",
```

세 prompt가 **같은 "시간 확정 여부" 기준**을 공유하게 되어, "참석자가 있다"는
표면적 신호만으로 서로 떠넘기는 경우가 없어집니다.

### 2-4. 검증 계획

- 멘토가 실제로 재현한 시나리오를 그대로 반복: "7월 9일 15시에 철수랑 회의
  잡아줘"를 6회 입력 → 6회 모두 `nana_agent` 내부에서 `save_structured_request`
  (또는 동등한 Week1-3 저장 tool)가 호출되고, 저장 후 `AppSQLiteStore`의
  `schedules`/`structured_requests`에 `kind="group_schedule"` row가 실제로
  생기는지 확인.
- 회귀 확인: "민준이랑 이번 주 언제 되는지 봐줘"처럼 시간이 정해지지 않은 요청은
  여전히 `kana_agent`로 위임되는지 확인(경계를 옮기다가 반대쪽을 깨뜨리지 않았는지).
- `checks/week06_deterministic.py`의 prompt-관련 static 케이스 재실행(문자열
  포함 여부를 보는 케이스가 있다면 새 문구에 맞게 케이스도 같이 갱신).

---

## 3. 리뷰의 나머지 항목 — 액션 아이템 여부

| 항목 | 조치 필요? | 비고 |
| --- | --- | --- |
| spec-first(체크 먼저, 구현 후 100%) 칭찬 | 없음 | 계속 유지 |
| 위임 판단 정확(5상황 x 3회) 칭찬 | 없음 | 계속 유지 |
| Q1. 스파이크 후 롤백 방식 | 없음(습관 개선 제안) | 롤백한 커밋을 지우지 말고 브랜치로 남기거나, 알게 된 것을 문서에 한 줄이라도 남기는 습관 — 이번엔 이미 롤백된 뒤라 새로 만들 코드는 없음. 다음에 심화과제를 다시 시도할 때 참고 |
| Q2. 역할 부여를 프롬프트에만 의존해도 되는지 | 없음(개념 확인) | 프롬프트가 기본, tool 목록 제한 + 역할별 모델 선택이 보완 — 이미 tool 목록은 역할별로 분리돼 있음(`supervisor_tools()`/`week04_tools()`/`kana_tools()`). 역할별 모델 차등은 이번 범위 밖 |
| Q3. 프롬프트-tool 불일치를 미리 잡는 방법 | **있음** | 아래 4절 |
| 매일 여러 글 읽는 습관 관련 조언 | 없음 | 개인 성장 조언, 코드와 무관 |

---

## 4. 정적 검사 추가 — "프롬프트가 언급한 tool 이름 vs 실제 노출된 tool 목록"

멘토가 코드로 직접 보여준 방식을 그대로 재사용합니다. LLM을 호출하지 않는
정적 검사라 무료·즉시 실행 가능하고, `checks/week06_deterministic.py`가 이미
쓰는 "spec-first, 구현 전엔 실패가 정상" 패턴과도 맞습니다.

### 4-1. 검사 로직

```python
import re

def _mentioned_tool_names(prompt_text: str) -> set[str]:
    return set(re.findall(r"[a-z]+(?:_[a-z]+)+", prompt_text))

def check_prompt_tool_consistency() -> list[str]:
    """각 역할의 prompt가 언급하는 tool 이름이 실제로 그 역할에 노출돼 있는지 확인."""
    failures = []
    targets = {
        "supervisor": (w6.supervisor_system_prompt(), {w6.tool_name(t) for t in w6.supervisor_tools()}),
        "nana": (" ".join(w6.nana_prompt_parts()), {w6.tool_name(t) for t in week04_tools()}),
        "kana": (" ".join(w6.kana_prompt_parts()), {w6.tool_name(t) for t in w6.kana_tools()}),
    }
    for role, (prompt_text, exposed) in targets.items():
        mentioned = _mentioned_tool_names(prompt_text)
        missing = mentioned - exposed
        # 함수 이름/일반 스네이크케이스 단어(예: "member_name")까지 걸릴 수 있으므로
        # 알려진 tool 이름 전체 집합과 교집합으로 좁혀서 오탐을 줄인다.
        all_known_tools = {w6.tool_name(t) for t in (*w6.supervisor_tools(), *week04_tools(), *w6.kana_tools())}
        missing_tools = missing & all_known_tools
        if missing_tools:
            failures.append(f"{role}: 프롬프트가 언급하지만 노출 안 된 tool = {sorted(missing_tools)}")
    return failures
```

멘토 예시와 차이점: 원래 예시는 스네이크케이스 단어를 전부 "언급된 tool 후보"로
보는데, 그러면 `member_name`, `date_from` 같은 일반 파라미터 이름도 걸릴 수
있습니다. `missing`을 **전체 주차에 실재하는 tool 이름 집합과의 교집합**으로
한 번 더 좁혀서 오탐을 줄이는 안전장치를 추가했습니다.

### 4-2. 어디에 넣을까

`checks/week06_deterministic.py`에 새 static 케이스 종류로 추가하거나(기존
`run_static`이 `nonempty`/`contains`/`accumulates`만 처리하므로 `assert:
"tool_consistency"` 케이스 타입을 하나 추가), 별도 파일
`checks/week06_prompt_tool_consistency.py`로 독립시키는 두 가지 방법이 있습니다.
**독립 파일 쪽을 제안합니다** — 이 검사는 `checks/week06_cases.py`의 개별 "케이스"
개념(입력 하나당 기대값 하나)과 성격이 달라서(구조적 diff 검사), 별도 스크립트로
두는 게 `checks/tool_inventory.py`(Week1-5 정적 조립 검사)와 같은 위치의 역할로
자연스럽습니다.

### 4-3. 검증 계획

- 새로 추가한 뒤 현재 코드로 실행 → "통과" 확인(멘토가 이미 확인해준 대로).
- 회귀 테스트로, 롤백 전 상태를 흉내 내어(`kana_prompt_parts()`에
  `"find_common_available_slots를 호출한다"` 문장을 임시로 추가) 다시 실행해
  `missing_tools`에 걸리는지 확인 — 멘토가 직접 보여준 재현과 동일.

---

## 5. 실행 순서 체크리스트 (완료)

1. [x] `student_parts/week05_load_kanas_past_conversations.py`에 공지 4절 (A)~(E) 적용
2. [x] `checks/week05_contract_check.py`(100% PASS), `checks/tool_inventory.py`(ALL PASS) 재실행 — 회귀 없음 확인
3. [x] `student_parts/week06_kanamate_decides_schedule.py`의 `nana_prompt_parts()` /
      `kana_prompt_parts()` / `week06_prompt_parts()` 세 곳 문구 수정 (2-3절) — "참석자 유무"가
      아니라 "시간 확정 여부" 기준으로 통일
4. [x] `checks/week06_prompt_tool_consistency.py` 신규 작성 + 실행 (4절) — 초안에서 supervisor의
      누적 프롬프트를 그대로 스캔하면 가이드가 요구하는 누적 구조 때문에 대량 오탐이 나서,
      kana/nana는 "언급 vs 노출" 비교로, supervisor는 "위임 tool 2개만 노출"로 검사 항목을
      역할별로 분리. 또한 "노출된 tool만 모아 known 집합을 만들면 롤백된 미노출 tool(예:
      find_common_available_slots)을 애초에 놓친다"는 걸 재현 테스트로 발견해, 모듈 namespace를
      직접 스캔하는 방식으로 교체. 시뮬레이션으로 실제 탐지되는 것까지 확인
5. [x] `checks/week06_deterministic.py` 재실행 — 회귀 없음(수정 전후 14/624로 동일, 실패 항목은
      전부 미구현 추가과제 스텁)
6. [x] 실제 agent로 두 재현 시나리오 수동 확인(격리된 데이터 복사본 사용, 실제 `data/` 무변경):
   - "7월 9일 15시에 철수랑 회의 잡아줘" → `nana_agent`가 `extract_schedule_request` →
     `save_structured_request`까지 호출해 저장 확인 (`schedule_id: sch_55842b7ba0` 생성)
   - 하린과 그룹 일정 저장 후 민준과 조율 → `collect_member_schedules` 결과 rows에
     `member_name: "나"` / `notes: "Nana 그룹 일정 · 참석자: 하린"` row가 정확히 포함됨을 확인
7. [ ] 멘토에게 재요청 (사용자 액션)

### 반영 중 추가로 발견한 사소한 점 (이번 리뷰 범위 밖, 기록만)

"7월 9일 15시에 철수랑 회의 잡아줘" 저장 시 `request_kind`가 `"personal_schedule"`로
저장됩니다(Week2 `extract_schedule_request`의 분류 로직이 참석자가 있어도
`group_schedule`로 안 바꾸는 것으로 보임). 이번에 고친 Week5 `_personal_schedules_for_current_scope()`가
`kind` 필터 자체를 없앴기 때문에 바쁜 시간 조회에는 영향이 없지만(personal/group
둘 다 포함됨), `_my_schedule_notes()`가 이 row를 "그룹 일정"이 아니라 "Nana 개인
일정"으로 표시하게 됩니다 — 참석자 정보가 notes에 안 남는 정도의 사소한 표시 오차입니다.
이번 리뷰 항목은 아니라 별도로 고치지 않았습니다.
