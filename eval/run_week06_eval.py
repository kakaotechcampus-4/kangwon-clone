"""Week6 supervisor 위임 라우팅 평가: 케이스별로 어떤 하위 agent(nana/kana)가 선택됐는지,
그 하위 agent 내부에서 기대한 tool이 호출됐는지 확인한다.

정답 있는 문제(어떤 agent/inner tool이 선택돼야 하는지)만 자동으로 체크하고, 최종 답변 문장의
품질(표현/인용 방식)은 사람이 answer 필드를 직접 읽고 판단한다.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixed.session_scope import conversation_session_scope
from fixed.week_agent_registry import run_active_week_agent

CASES_PATH = Path(__file__).resolve().with_name("week06_cases.json")


def run_case(case: dict, index: int) -> dict:
    conversation_id = f"eval_week06_{case['id']}_{index}"
    messages = [{"role": "user", "content": case["query"]}]
    with conversation_session_scope(conversation_id):
        result = run_active_week_agent(6, messages)

    trace = result.trace
    selected_agent = trace.get("supervisor_selected_agent")
    inner_tool_names = trace.get("inner_tool_names") or []
    expected_agent = case["expected_agent"]
    expected_inner_tool = case.get("expected_inner_tool")

    agent_ok = selected_agent == expected_agent
    if expected_inner_tool:
        match_mode = case.get("inner_match", "any")
        expected_inner_list = (
            expected_inner_tool if isinstance(expected_inner_tool, list) else [expected_inner_tool]
        )
        if match_mode == "any":
            inner_ok = any(tool in inner_tool_names for tool in expected_inner_list)
        else:
            inner_ok = all(tool in inner_tool_names for tool in expected_inner_list)
    else:
        inner_ok = True

    passed = agent_ok and inner_ok

    return {
        "id": case["id"],
        "query_type": case["query_type"],
        "query": case["query"],
        "expected_agent": expected_agent,
        "selected_agent": selected_agent,
        "expected_inner_tool": expected_inner_tool,
        "inner_tool_names": inner_tool_names,
        "passed": passed,
        "answer": result.answer,
    }


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results = [run_case(case, index) for index, case in enumerate(cases)]

    print("\n=== Week6 supervisor 위임 라우팅 평가 결과 ===")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"\n[{status}] {r['id']} ({r['query_type']})")
        print(f"  query: {r['query']}")
        print(f"  기대 agent: {r['expected_agent']} / 실제 선택: {r['selected_agent']}")
        if r["expected_inner_tool"]:
            print(f"  기대 inner tool: {r['expected_inner_tool']} / 실제 호출: {r['inner_tool_names']}")
        print(f"  answer: {r['answer'][:200]}")

    passed_count = sum(1 for r in results if r["passed"])
    print(f"\n{passed_count}/{len(results)} 통과 (라우팅 기준, 답변 표현 품질은 위 answer를 직접 확인)")


if __name__ == "__main__":
    main()
