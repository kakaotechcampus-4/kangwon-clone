"""Week 6 supervisor/위임 테스트 — Layer 1 (LLM 없이 결정적으로 검증한다).

Week 4/5 와 같은 2계층 원칙이다. 여기서 보는 것은 "위임 wrapper 가 계약대로
만들고 넘기는가"이고, "supervisor 가 알맞은 하위 agent 를 고르는가"는
Layer 2(tests/manual_week06_delegation.py)에서 통과율로 잰다.

6주차에서 계약이라고 부르는 것
  이 주차 wrapper 는 SQL 도 MCP 도 쓰지 않는다. 하는 일은 세 가지뿐이다 —
  하위 agent 를 한 번만 만들고, query 를 넘기고, 결과를 supervisor 가 읽을 수 있는
  JSON 으로 바꾸는 것. 그래서 검증할 게 "일정이 맞나"가 아니라
  "supervisor 가 볼 수 있는 형태로 나왔나"다.

  특히 kana_agent 의 final_slot_payload 를 여기서 본다. supervisor 는 하위 trace 를
  직접 읽지 않으므로, 이 끌어올리기가 빠지면 "조율은 됐는데 답변에는 시간이 없는"
  상태가 된다. 실제로 구현 중에 그 상태를 만들어봤고 눈으로는 구분이 안 됐다.

격리 방법
  하위 agent 를 fake 로 바꿔 끼운다(_NANA_SUBAGENT / _KANA_SUBAGENT).
  LLM 도 DB 도 타지 않으므로 반환 계약과 trace 끌어올리기를 단정할 수 있다.
  임시 DB 를 만드는 방법(week03 방식)은 여기서 의미가 없다 — 이 파일의 wrapper 는
  DB 를 안 보고, 하위 agent 가 무엇을 부르는지는 프롬프트가 정하는 일이라 Layer 2 몫이다.

일부러 여기 안 넣은 것
  - 조율만 요청했을 때 저장 tool 이 불리는지: prompt 판단이라 Layer 2 에서 통과율로 잰다.
    구현 중에 run 마다 결과가 갈렸던 항목이고, 그래서 단정하는 테스트로 만들면 안 된다.
  - 실제 위임 정확도: 같은 이유로 Layer 2.
  - 추가과제 tool 의 후보 검증 로직: fixed/schedule_decision.py 담당이다.

실행:
  uv run pytest tests/test_week06_supervisor.py -q
"""

import inspect
import json
from typing import Any

import pytest

import student_parts.week06_kanamate_decides_schedule as week06
from fixed.runtime_clock import current_app_date_iso
from student_parts.week04_retrieve_nanas_memory import week04_prompt_parts
from student_parts.week06_kanamate_decides_schedule import (
    kana_agent,
    kana_system_prompt,
    kana_tools,
    nana_agent,
    nana_system_prompt,
    supervisor_system_prompt,
    supervisor_tools,
    week06_prompt_parts,
)


# --- fake 하위 agent --------------------------------------------------------
# extract_agent_events(fixed/langchain_trace.py:114)가 읽는 최소 형태만 맞춘다.
#   tool_call  : message.tool_calls = [{"name","args","id"}]
#   tool_result: message.type == "tool" 이고 content 는 JSON 문자열


class FakeAI:
    type = "ai"

    def __init__(self, tool_calls: list[dict[str, Any]] | None = None, content: str = ""):
        self.tool_calls = tool_calls or []
        self.content = content


class FakeToolMessage:
    type = "tool"
    tool_calls: list[dict[str, Any]] = []

    def __init__(self, name: str, payload: Any):
        self.name = name
        self.tool_call_id = f"call_{name}"
        self.content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)


class FakeSubAgent:
    """invoke 를 받으면 미리 정한 메시지 목록을 그대로 돌려준다."""

    def __init__(self, messages: list[Any]):
        self.messages = messages
        self.calls: list[dict[str, Any]] = []

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        return {"messages": self.messages}


def answer_only(text: str) -> list[Any]:
    return [FakeAI(content=text)]


def with_tool(tool_name: str, payload: Any, answer: str) -> list[Any]:
    return [
        FakeAI(tool_calls=[{"name": tool_name, "args": {}, "id": f"call_{tool_name}"}]),
        FakeToolMessage(tool_name, payload),
        FakeAI(content=answer),
    ]


@pytest.fixture(autouse=True)
def reset_subagents():
    """모듈 전역 캐시를 매 테스트마다 비운다. 안 비우면 앞 테스트의 fake 가 남는다."""

    week06._NANA_SUBAGENT = None
    week06._KANA_SUBAGENT = None
    yield
    week06._NANA_SUBAGENT = None
    week06._KANA_SUBAGENT = None


def payload_of(tool: Any, args: dict[str, Any]) -> dict[str, Any]:
    return json.loads(tool.invoke(args))


# --- 도구 배선 --------------------------------------------------------------


def test_supervisor는_하위_agent_두_개만_본다():
    """과제의 핵심 제약이다(가이드 43행). 다른 tool 이 새면 위임 구조가 무너진다."""

    assert [tool.name for tool in supervisor_tools()] == ["nana_agent", "kana_agent"]


def test_미구현_tool이_kana에_노출되지_않는다():
    """추가과제를 구현하지 않으려면 kana_tools() 에서 빼라는 게 가이드 지시다(85행).

    판정을 소스의 TODO 마커로 하는 이유는 5주차 테스트와 같다 —
    본문이 `...` 뿐인 함수는 바이트코드로 구별할 수 없다.
    구현하든 목록에서 빼든 둘 중 하나를 하면 통과한다.
    """

    def is_todo(tool: Any) -> bool:
        try:
            return "TODO" in inspect.getsource(tool.func)
        except (OSError, TypeError):  # 소스를 못 읽으면 판정하지 않는다
            return False

    unimplemented = sorted(tool.name for tool in kana_tools() if is_todo(tool))

    assert not unimplemented, f"미구현 tool 이 Kana 에 노출돼 있다: {unimplemented}"


# --- prompt 상속 ------------------------------------------------------------


def test_kana_prompt에_오늘_날짜가_있다():
    """회귀 테스트. 이게 없어서 Kana 가 "7월 14일"을 2024년으로 잡았다.

    kana_prompt_parts 만 다른 주차를 누적하지 않으므로, 앞 주차 prompt 에 있던
    오늘 날짜가 Kana 에는 전달되지 않는다. 날짜를 모르면 연도를 지어낸다.
    """

    assert current_app_date_iso() in kana_system_prompt()


def test_세_agent의_prompt는_서로_다르다():
    """하위 agent 는 supervisor prompt 를 공유하지 않는다(가이드 71행).

    세 값이 같아지면 위임 구조는 남아 있어도 역할 분담이 사라진다.
    """

    prompts = {supervisor_system_prompt(), nana_system_prompt(), kana_system_prompt()}

    assert len(prompts) == 3


def test_nana는_4주차를_누적하고_kana는_누적하지_않는다():
    """누적 규칙 자체를 고정한다. 여기가 위 회귀 테스트의 근거다."""

    nana = nana_system_prompt()
    kana = kana_system_prompt()
    # join_system_prompt(week01:39)가 조각마다 strip 을 걸므로 비교도 strip 한 값으로 한다.
    week04_only = [part.strip() for part in week04_prompt_parts() if part.strip()]

    assert week04_only, "4주차 prompt 조각이 비어 있으면 이 테스트는 의미가 없다"
    assert all(part in nana for part in week04_only)
    assert not any(part in kana for part in week04_only)


def test_supervisor_prompt는_week06_조각을_담는다():
    supervisor = supervisor_system_prompt()

    assert all(part.strip() in supervisor for part in week06_prompt_parts() if part.strip())


# --- 위임 wrapper 반환 계약 -------------------------------------------------


def test_nana_agent는_answer와_trace와_도구이름을_돌려준다():
    week06._NANA_SUBAGENT = FakeSubAgent(
        with_tool("personal_list_saved_schedules", {"ok": True, "rows": []}, "일정은 없습니다.")
    )

    payload = payload_of(nana_agent, {"query": "내 일정 알려줘"})

    assert payload["selected_agent"] == "nana_agent"
    assert payload["answer"] == "일정은 없습니다."
    assert payload["inner_tool_names"] == ["personal_list_saved_schedules"]
    assert payload["trace"], "trace 가 비면 위임이 제대로 됐는지 확인할 수 없다"


def test_query가_하위_agent에_user_메시지로_전달된다():
    fake = FakeSubAgent(answer_only("네."))
    week06._NANA_SUBAGENT = fake

    nana_agent.invoke({"query": "장보기 할일 추가해줘"})

    assert fake.calls == [{"messages": [{"role": "user", "content": "장보기 할일 추가해줘"}]}]


def test_inner_tool_names는_호출_순서를_보존한다():
    """Layer 2 판정이 이 순서를 근거로 쓴다. 순서가 섞이면 흐름을 못 본다."""

    week06._KANA_SUBAGENT = FakeSubAgent(
        [
            FakeAI(tool_calls=[{"name": "collect_member_schedules", "args": {}, "id": "a"}]),
            FakeToolMessage("collect_member_schedules", {"rows": []}),
            FakeAI(tool_calls=[{"name": "list_shared_schedules", "args": {}, "id": "b"}]),
            FakeToolMessage("list_shared_schedules", {"rows": []}),
            FakeAI(content="정리했습니다."),
        ]
    )

    payload = payload_of(kana_agent, {"query": "민준 일정 알려줘"})

    assert payload["inner_tool_names"] == ["collect_member_schedules", "list_shared_schedules"]


def test_하위_agent는_한_번만_만들어진다(monkeypatch):
    """가이드가 "만들거나 재사용" 이라고 한 부분이다(74행).

    매 호출마다 create_agent 를 부르면 위임할 때마다 agent 를 새로 조립한다.
    """

    created: list[str] = []

    def fake_create_agent(**kwargs: Any) -> Any:
        created.append(str(kwargs.get("system_prompt", ""))[:10])
        return FakeSubAgent(answer_only("네."))

    monkeypatch.setattr(week06, "create_agent", fake_create_agent)
    monkeypatch.setattr(week06, "chat_model", lambda: object())

    nana_agent.invoke({"query": "첫 번째"})
    nana_agent.invoke({"query": "두 번째"})

    assert len(created) == 1


# --- kana_agent 의 final_slot 끌어올리기 ------------------------------------


def test_kana_agent가_final_slot을_trace에서_끌어올린다():
    """supervisor 는 하위 trace 를 안 읽는다. 여기서 안 올리면 답변에 시간이 안 나온다."""

    decided = {
        "final_slot": "2026-07-14 15:00-16:00",
        "reason": "둘 다 비는 시간",
        "candidates": ["2026-07-14 15:00-16:00"],
        "needs_agent_selection": False,
    }
    week06._KANA_SUBAGENT = FakeSubAgent(with_tool("decide_final_slot", decided, "7월 14일 3시로 정했습니다."))

    payload = payload_of(kana_agent, {"query": "민준이랑 시간 맞춰줘"})

    assert payload["final_slot_payload"]["final_slot"] == "2026-07-14 15:00-16:00"
    assert payload["final_slot_payload"]["needs_agent_selection"] is False


def test_확정하지_못한_경우도_그대로_올린다():
    """후보가 없을 때 final_slot 을 임의로 채우면 없는 시간을 답하게 된다."""

    undecided = {"final_slot": None, "reason": "가능한 시간이 없음", "candidates": [], "needs_agent_selection": True}
    week06._KANA_SUBAGENT = FakeSubAgent(with_tool("decide_final_slot", undecided, "가능한 시간이 없습니다."))

    payload = payload_of(kana_agent, {"query": "민준이랑 시간 맞춰줘"})

    assert payload["final_slot_payload"]["final_slot"] is None
    assert payload["final_slot_payload"]["needs_agent_selection"] is True


def test_결정_tool을_두_번_부르면_마지막이_남는다():
    """다시 물어서 재확정하는 경우 나중 결정이 맞다.

    구현 중에 Kana 가 같은 조율을 두 번 돌리면서 두 번째에 final_slot 을 비워 넘긴 적이 있다.
    그때 확정이 사라지는 걸 보고 이 규칙을 의도적으로 고른 것이라 테스트로 남긴다.
    """

    first = {"final_slot": "2026-07-14 10:00-11:00", "candidates": [], "needs_agent_selection": False}
    second = {"final_slot": "2026-07-15 14:00-15:00", "candidates": [], "needs_agent_selection": False}
    week06._KANA_SUBAGENT = FakeSubAgent(
        [
            FakeAI(tool_calls=[{"name": "decide_final_slot", "args": {}, "id": "a"}]),
            FakeToolMessage("decide_final_slot", first),
            FakeAI(tool_calls=[{"name": "decide_final_slot", "args": {}, "id": "b"}]),
            FakeToolMessage("decide_final_slot", second),
            FakeAI(content="7월 15일로 바꿨습니다."),
        ]
    )

    payload = payload_of(kana_agent, {"query": "다른 날로 바꿔줘"})

    assert payload["final_slot_payload"]["final_slot"] == "2026-07-15 14:00-15:00"


def test_final_decision도_끌어올린다():
    """호환용 propose_group_schedule 경로다. 키 이름이 달라서 따로 본다."""

    body = {"ok": True, "final_decision": {"title": "회의", "status": "confirmed"}}
    week06._KANA_SUBAGENT = FakeSubAgent(with_tool("propose_group_schedule", body, "확정했습니다."))

    payload = payload_of(kana_agent, {"query": "회의 확정해줘"})

    assert payload["final_decision_payload"]["status"] == "confirmed"


def test_결정_tool이_없으면_두_payload가_비어_있다():
    """단순 조회 위임에서 엉뚱한 값이 올라오면 supervisor 가 없는 시간을 답한다."""

    week06._KANA_SUBAGENT = FakeSubAgent(with_tool("search_previous_conversations", {"rows": []}, "찾지 못했습니다."))

    payload = payload_of(kana_agent, {"query": "시우가 발표 얘기한 대화 찾아줘"})

    assert payload["final_slot_payload"] is None
    assert payload["final_decision_payload"] is None
