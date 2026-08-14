# Week 6 구현 가이드 — 구현 팁 + 코드 설명

`student_parts/week06_kanamate_decides_schedule.py`를 구현하기 위한 문서. 3주차 멘토가 예고했던 **supervisor(감독) 구조**가 여기서 나온다.

---

## 0. 한 줄 요약

지금까지는 **한 agent가 모든 tool을 다 들고** 처리했다. Week 6은 그걸 **supervisor 1명 + 하위 agent 2명(Nana, Kana)** 으로 쪼갠다. supervisor는 실무 tool을 하나도 못 보고, **`nana_agent`/`kana_agent` 딱 2개 tool만** 보고 "누구한테 시킬지"만 정한다.

```
사용자 → supervisor (nana_agent / kana_agent 중 위임)
              ├─ nana_agent → Nana 하위 agent (week04_tools: 개인 일정/저장/RAG)
              └─ kana_agent → Kana 하위 agent (kana_tools: 외부 멤버 일정/공통 시간 결정)
```

**Week 6은 1~5주차 코드를 다시 쓰지 않는다.** 이전 tool을 import해서 역할별로 `kana_tools()`/`supervisor_tools()`에 조립하고, **prompt로 역할 분담을 정의하는 게 핵심**이다.

---

## 1. 구현 대상 (메인 / 추가)

### 메인과제
| 대상 | 무엇 | 핵심 |
| --- | --- | --- |
| `week06_prompt_parts` (supervisor) | `week05_prompt_parts()` 누적 + supervisor 지시 | 직접 처리 금지, nana/kana로만 위임 |
| `nana_prompt_parts` | `week04_prompt_parts()` 누적 + Nana 역할 | 개인 일정/저장/RAG. 그룹 조율은 "담당 아님" |
| `kana_prompt_parts` | **누적 없음 — 처음부터 작성** | 외부 멤버 일정/공통 시간/그룹 조율. 확정 저장은 "Nana 담당" |
| `supervisor_system_prompt` | 위 조각 + supervisor 실행 역할 | nana/kana 중 하나 호출 후 그 결과만 근거로 답 |
| `nana_agent` (tool) | Nana 하위 agent 실행 wrapper | answer/trace/inner_tool_names JSON 반환 |
| `kana_agent` (tool) | Kana 하위 agent 실행 wrapper | + final_slot_payload/final_decision_payload 끌어올림 |

### 추가과제 (안 하면 `kana_tools()`·Kana 프롬프트에서 두 tool 제거)
| 대상 | 무엇 |
| --- | --- |
| `FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION` / `DECIDE_FINAL_SLOT_DESCRIPTION` | 두 tool의 description 상수 (agent가 언제·어떤 인자로 부를지 판단하는 유일한 근거) |
| `find_common_available_slots_dict` / `find_common_available_slots` / `decide_final_slot` | 공통 가능 시간 후보 검증 + 최종 시간 기록 |

이미 완성돼 있어 **손대지 않는 것**: `propose_group_schedule`(호환용, `kana_tools()`에 미포함), `extract_langchain_trace`, `_tool_call_names`, `tool_name`, 각종 Input 스키마, `build_langchain_supervisor_agent`, `kana_tools`/`supervisor_tools`/`agent_tool_names`.

---

## 2. 가장 중요한 개념 2가지

### 개념 A — supervisor는 실무 tool을 못 본다
`supervisor_tools()`는 `[nana_agent, kana_agent]` 뿐이다. supervisor는 `personal_list_saved_schedules`나 `collect_member_schedules`를 **직접 부를 수 없다.** 모든 실무는 하위 agent를 통해서만 일어난다. 그래서 supervisor 프롬프트의 유일한 일은 **"이 요청은 Nana? Kana?" 라우팅**이다.
- 개인 일정/할일/알림/참고자료/앱 대화 → **Nana**
- 외부 멤버 일정/공유 일정/여러 사람 공통 시간/그룹 조율 → **Kana**

### 개념 B — "계산은 agent가, 검증은 tool이" (추가과제 핵심)
`find_common_available_slots`/`decide_final_slot`는 **Python이 최적 시간을 계산해주지 않는다.** Kana **agent가** busy_rows를 읽고 후보(`candidate_slots`)와 최종 시간(`final_slot`)을 **직접 골라 인자로 넘긴다.** Python tool은 그걸 받아 `fixed/schedule_decision.py`로 **검증·기록만** 한다(겹치는 후보 제거, 업무시간·기간·날짜 범위 밖 제거).

→ 그래서 **tool description이 전부다.** description에 "이 tool은 후보를 계산하지 않는다. agent가 busy_rows를 보고 직접 채워라"가 없으면, agent는 계산을 tool에 떠넘기고 빈손으로 부른다. description과 Python 구현이 **같은 계약**을 말해야 한다.

---

## 3. 코드 설명 (구현 스케치)

### 3-1. 프롬프트 4종 (메인)
- `week06_prompt_parts()`: `[*week05_prompt_parts(), "supervisor 위임 규칙..."]`. supervisor는 직접 tool 실행 안 하고 nana/kana 중 하나로만 위임, 라우팅 기준 명시.
- `nana_prompt_parts()`: `[*week04_prompt_parts(), "너는 Nana. 개인 일정/저장/RAG 담당. 그룹/외부 멤버 조율은 담당 아니라고 짧게 답."]`
- `kana_prompt_parts()`: **`[...]` 빈 리스트에서 시작** → Kana 역할을 처음부터. "너는 Kana. 외부 멤버 대화/일정, 공유 일정, 여러 사람 공통 가능 시간·최종 시간 결정 담당. 확정 일정 저장은 Nana 담당. (추가과제 시) 후보 검증엔 find_common_available_slots, 최종 결정엔 decide_final_slot을 이어서 호출."
- `supervisor_system_prompt()`: 이미 `join_system_prompt([*week06_prompt_parts(), TODO])` 골격. TODO에 "반드시 nana_agent 또는 kana_agent 중 하나를 호출한 뒤 그 결과만 근거로 답한다" 추가.

> 함정: **하위 agent는 supervisor 프롬프트를 공유하지 않는다.** Nana/Kana가 각자 자기 역할을 스스로 알아야 하므로, nana/kana_prompt_parts에 역할을 확실히 써야 한다. 특히 `kana_prompt_parts`는 누적이 없어 비면 Kana가 아무 역할도 모른다.

### 3-2. `nana_agent(query)` (메인)
```python
@tool(args_schema=AgentQueryInput)
def nana_agent(query: str) -> str:
    global _NANA_SUBAGENT
    if _NANA_SUBAGENT is None:
        _NANA_SUBAGENT = create_agent(model=chat_model(), tools=week04_tools(), system_prompt=nana_system_prompt())
    result = _NANA_SUBAGENT.invoke({"messages": [{"role": "user", "content": query}]})
    events = extract_agent_events(result)
    return json.dumps({
        "ok": True, "tool_name": "nana_agent", "selected_agent": "nana_agent",
        "answer": extract_final_text(result),
        "trace": {"events": events},
        "inner_tool_names": _tool_call_names(events),
    }, ensure_ascii=False)
```
- `inner_tool_names`가 있어야 supervisor의 `extract_langchain_trace`가 하위 tool 호출을 끌어올린다.

### 3-3. `kana_agent(query)` (메인)
`nana_agent`와 같되, Kana 하위 trace에서 **최종 시간 payload를 끌어올린다.**
```python
@tool(args_schema=AgentQueryInput)
def kana_agent(query: str) -> str:
    global _KANA_SUBAGENT
    if _KANA_SUBAGENT is None:
        _KANA_SUBAGENT = create_agent(model=chat_model(), tools=kana_tools(), system_prompt=kana_system_prompt())
    result = _KANA_SUBAGENT.invoke({"messages": [{"role": "user", "content": query}]})
    events = extract_agent_events(result)
    final_slot_payload = None
    final_decision_payload = None
    for event in events:
        content = event.get("content")
        if isinstance(content, dict):
            if "final_slot" in content:            # decide_final_slot 결과
                final_slot_payload = content
            if content.get("final_decision"):      # (호환) propose_group_schedule 결과
                final_decision_payload = content["final_decision"]
    return json.dumps({
        "ok": True, "tool_name": "kana_agent", "selected_agent": "kana_agent",
        "answer": extract_final_text(result),
        "trace": {"events": events},
        "inner_tool_names": _tool_call_names(events),
        "final_slot_payload": final_slot_payload,
        "final_decision_payload": final_decision_payload,
    }, ensure_ascii=False)
```

### 3-4. 추가과제 — 두 tool description
`FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION`에 반드시 담을 것:
- "이 tool은 후보 시간을 **계산하지 않는다.** 너(agent)가 busy_rows를 읽고 `candidate_slots`를 직접 채워 넘겨라."
- 각 후보 형식: `date(YYYY-MM-DD)`, `start_time(HH:MM)`, `end_time(HH:MM)`, `duration_minutes`, `reason`.
- 후보는 **어떤 busy row와도 겹치면 안 되고**, `busy_rows`는 앞선 조회 tool output에서 **복사**해 넘겨라.
- 여기서 끝내지 말고 **`decide_final_slot`을 이어서** 호출하라.

`DECIDE_FINAL_SLOT_DESCRIPTION`에 담을 것:
- "이 tool은 최종 시간을 **자동 선택하지 않는다.** `selected_index` 또는 `selected_slot`과 `final_slot`을 네가 직접 골라 넘겨라."
- `final_slot` 형식: `'YYYY-MM-DD HH:MM-HH:MM'`. 아직 못 골랐으면 `final_slot=null`, `needs_agent_selection=true`.
- 근거로 `candidate_slots`, `busy_rows`, `member_names`, `date_from`/`date_to`도 함께 넘겨라.

### 3-5. 추가과제 — 세 함수
```python
def find_common_available_slots_dict(member_names, date_from, date_to, duration_minutes=60,
        workday_start="09:00", workday_end="18:00", limit=5, busy_rows=None,
        candidate_slots=None, llm_reason=None):
    members = normalize_external_member_names(member_names)
    if "나" not in members:            # 내 일정도 제약 → "나" 포함
        members = ["나", *members]
    d_from, d_to = normalize_date_bound(date_from), normalize_date_bound(date_to)
    if busy_rows is None:              # 없으면 직접 수집
        collected = json.loads(collect_member_schedules.invoke(
            {"member_names": member_names, "date_from": d_from, "date_to": d_to}))
        busy_rows = collected.get("rows", [])
    return find_common_available_slots_payload(
        member_names=members, date_from=d_from, date_to=d_to, busy_rows=busy_rows,
        duration_minutes=duration_minutes, workday_start=workday_start, workday_end=workday_end,
        limit=limit, candidate_slots=candidate_slots, llm_reason=llm_reason)

@tool(description=FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION, args_schema=FindCommonAvailableSlotsInput)
def find_common_available_slots(...):
    return json.dumps(find_common_available_slots_dict(...), ensure_ascii=False)

@tool(description=DECIDE_FINAL_SLOT_DESCRIPTION, args_schema=DecideFinalSlotInput)
def decide_final_slot(...):
    # 직접 고르지 말고 인자를 그대로 payload 함수에 전달
    return json.dumps(decide_final_slot_payload(
        candidate_slots=candidate_slots, selected_slot=selected_slot, selected_index=selected_index,
        member_names=member_names, date_from=date_from, date_to=date_to, duration_minutes=duration_minutes,
        final_slot=final_slot, needs_agent_selection=needs_agent_selection, reason=reason, busy_rows=busy_rows),
        ensure_ascii=False)
```
- `find_common_available_slots_payload`가 실제 겹침 검증을 한다(`busy_rows_overlap`, 업무시간/기간/날짜 범위 필터). 반환에 `candidate_slots`(검증 통과분)·`busy_rows`·`members`가 남는다.
- `decide_final_slot_payload` 반환 top-level: `final_slot`, `reason`, `candidates`, `needs_agent_selection`. `selected_index`만 주면 그 index의 후보를 최종으로 해석, `final_slot`도 `selected_slot`도 없으면 `needs_agent_selection=True` 유지.

### 3-6. `fixed/schedule_decision.py` (읽기만, 수정 X)
- `CommonSlotCandidate`: `date/start_time/end_time/duration_minutes/reason`.
- `find_common_available_slots_payload(...)`: agent 후보를 검증(겹침/업무시간/기간/날짜)해 통과분만 남김.
- `decide_final_slot_payload(...)`: `final_slot` 또는 `selected_index/selected_slot`으로 최종 확정, 없으면 보류(`needs_agent_selection`).
- `normalize_date_bound(v)`: ISO datetime → 날짜만.

---

## 4. 구현 팁 / 함정 체크리스트

- **`kana_prompt_parts`는 빈 `[]`에서 시작** — Nana처럼 누적이 없다. 비워두면 Kana가 역할을 모른다. 반드시 채워라.
- **하위 agent는 supervisor 프롬프트를 못 본다** — 위임 규칙은 supervisor에, 각 역할은 nana/kana 프롬프트에 각각 써라.
- **supervisor는 실무 tool을 못 본다** — supervisor 프롬프트에서 `personal_list_saved_schedules` 같은 실무 tool 이름을 부르라고 쓰면 안 된다. "Nana/Kana에게 위임"만.
- **description = 계약**: 추가과제 두 tool은 description이 유일한 판단 근거. "계산은 네가, tool은 검증만", 인자 형식(candidate 5필드, final_slot 문자열)을 명시. description이 비면 agent가 빈 인자로 부른다.
- **"나" 포함**: 공통 시간엔 내 일정도 제약이므로 members에 "나"를 넣어야 내 busy time이 반영된다.
- **busy_rows 복사 유도**: agent가 앞선 `collect_member_schedules` 결과의 rows를 `busy_rows`로 복사해 넘기게 description에 명시. 안 넘기면 `find_common_available_slots_dict`가 `collect_member_schedules`를 다시 부른다(둘 다 안전하지만 흐름 이해).
- **최종 시간을 Python이 고르지 않게**: `decide_final_slot`은 인자 pass-through. 직접 `min()` 등으로 고르면 과제 취지(agent가 판단) 위반.
- **추가과제 안 할 거면**: `kana_tools()`에서 `find_common_available_slots`/`decide_final_slot` 제거 **+ Kana 프롬프트에서도 두 tool 언급 삭제**(안 그러면 없는 tool을 부르라고 지시하게 됨).
- **하위→supervisor payload 연결**: `kana_agent`가 `final_slot_payload`를 안 끌어올리면 supervisor의 `extract_langchain_trace`가 최종 시간을 못 잡는다. `nana_agent`/`kana_agent`는 `inner_tool_names`를 꼭 반환.
- **캐싱**: `_NANA_SUBAGENT`/`_KANA_SUBAGENT`/`_SUPERVISOR_AGENT` 전역으로 한 번만 build.

---

## 5. 검증 방법

- **메인**: `./run.sh --week6` → "내 일정 보여줘"는 supervisor trace에 `nana_agent` 선택 + Nana 하위 trace에 `personal_list_saved_schedules`. "철수·영희랑 회의 시간 잡아줘"는 `kana_agent` 선택. 위임이 엉뚱하면 **tool이 아니라 supervisor 프롬프트의 라우팅 기준**을 먼저 고친다.
- **추가**: 그룹 요청에서 Kana 하위 trace가 `collect_member_schedules`(또는 search/extract) → `find_common_available_slots` → `decide_final_slot`으로 이어지고, `final_slot_payload`가 최종 답변과 일치하는지 확인.
- (선택) `checks/tool_inventory.py`에 week6를 추가하면 스텁/회귀/프롬프트 언급 검사를 재사용할 수 있다. 단 week6는 supervisor가 `[nana_agent, kana_agent]`만 노출하므로 인벤토리 규칙(구현 tool이 프롬프트에 언급)을 그대로 쓰긴 어렵고, Kana/Nana 하위 tool 목록은 `agent_tool_names("kana_agent")`로 따로 확인하는 방식이 맞다.

---

## 6. 지난 주차 교훈 이어가기 (멘토링 반영)

- **프롬프트가 동작을 좌우한다**(4·5주차 반복): 위임/역할 프롬프트가 곧 스펙. 위임이 틀리면 프롬프트부터.
- **기준=스펙**(멘토 2-4): 검증 케이스를 만들 때 "supervisor가 실무 tool을 직접 부르려 하면?", "kana_prompt가 비면?", "description이 비면 agent가 빈 인자로 부르는가?"를 케이스로.
- **임계값=상한**(멘토 2-5): 위임 정확도(라우팅)와 그룹 조율 성공률을 나눠 재고, 통과 후에도 실패 위임 케이스를 눈으로.
- **테스트 안 고치기 / 변경 범위 확인**(2-3, 2-6): `student_parts/week06`·`checks`만.
