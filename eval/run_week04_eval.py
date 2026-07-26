"""Week4 tool 라우팅 평가: 케이스별로 실제 agent를 돌려 기대한 tool이 호출됐는지 확인한다.

정답 있는 문제(어떤 tool이 불려야 하는지)만 자동으로 체크하고, 최종 답변 문장의 품질(표현/인용 방식)은
사람이 answer 필드를 직접 읽고 판단한다.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixed.session_scope import conversation_session_scope
from fixed.week_agent_registry import run_active_week_agent

CASES_PATH = Path(__file__).resolve().with_name("week04_cases.json")


def called_tool_names(trace: dict) -> list[str]:
    return [event["tool_name"] for event in trace.get("events", []) if event.get("event") == "tool_call"]


def run_case(case: dict, index: int) -> dict:
    conversation_id = f"eval_week04_{case['id']}_{index}"
    messages = [{"role": "user", "content": case["query"]}]
    with conversation_session_scope(conversation_id):
        result = run_active_week_agent(4, messages)

    called = called_tool_names(result.trace)
    expected = case["expected_tools"]
    match_mode = case.get("match", "all")
    if match_mode == "any":
        passed = any(tool in called for tool in expected)
        missing = [] if passed else expected
    else:
        missing = [tool for tool in expected if tool not in called]
        passed = not missing

    return {
        "id": case["id"],
        "query_type": case["query_type"],
        "query": case["query"],
        "expected_tools": expected,
        "match": match_mode,
        "called_tools": called,
        "missing_tools": missing,
        "passed": passed,
        "answer": result.answer,
    }


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results = [run_case(case, index) for index, case in enumerate(cases)]

    print("\n=== Week4 tool 라우팅 평가 결과 ===")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"\n[{status}] {r['id']} ({r['query_type']})")
        print(f"  query: {r['query']}")
        match_label = "any" if r["match"] == "any" else "all"
        print(f"  기대 tool({match_label}): {r['expected_tools']} / 실제 호출: {r['called_tools']}")
        if not r["passed"]:
            print(f"  누락: {r['missing_tools']}")
        print(f"  answer: {r['answer'][:200]}")

    passed_count = sum(1 for r in results if r["passed"])
    print(f"\n{passed_count}/{len(results)} 통과 (라우팅 기준, 답변 표현 품질은 위 answer를 직접 확인)")


if __name__ == "__main__":
    main()
