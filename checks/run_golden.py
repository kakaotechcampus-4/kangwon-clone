"""Golden 케이스 실행기 (docs/ASSIGNMENT_CHECK_DESIGN.md Tier 2).

실제 `build_week_agent()` + 실제 LLM + 실제 embedding API를 호출해 tool-selection
정확도를 측정합니다. 앱과 동일한 경로(`run_active_week_agent`)를 그대로 재사용합니다.

데이터 격리: 실제 data/ 파일을 임시 폴더로 복사한 뒤 CONFIG 경로를 그 복사본으로
패치하고 나서 student_parts 모듈을 로드합니다. 실제 data/ 는 변경되지 않습니다.

실행:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/run_golden.py            # 전체
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/run_golden.py --limit 12 # 앞 12개만(빠른 점검)
PROXY_TOKEN(.env)이 없으면 LLM 호출이 불가하므로 건너뜁니다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from checks.golden_cases import CASES, CONVERSATION, TARGET_TOOLS
from fixed.config import CONFIG

CONTRACT_KEYS = {"hits", "rows", "context", "rag_backend", "sync"}


def _isolate_data() -> Path:
    """실제 data/ 를 임시 폴더로 복사하고 CONFIG 경로를 그쪽으로 돌립니다."""

    tmp = Path(tempfile.mkdtemp(prefix="golden_data_"))
    for src in (CONFIG.app_db_path, CONFIG.external_db_path):
        if Path(src).exists():
            shutil.copy2(src, tmp / Path(src).name)
    if Path(CONFIG.chroma_dir).exists():
        shutil.copytree(CONFIG.chroma_dir, tmp / "chroma")
    object.__setattr__(CONFIG, "app_db_path", tmp / Path(CONFIG.app_db_path).name)
    object.__setattr__(CONFIG, "external_db_path", tmp / Path(CONFIG.external_db_path).name)
    object.__setattr__(CONFIG, "chroma_dir", tmp / "chroma")
    return tmp


def _called_tools_and_results(trace: dict) -> tuple[list[str], dict[str, object]]:
    events = trace.get("events", []) if isinstance(trace, dict) else []
    called = [e.get("tool_name") for e in events if e.get("event") == "tool_call"]
    results = {e.get("tool_name"): e.get("content") for e in events if e.get("event") == "tool_result"}
    return [name for name in called if name], results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="앞 N개만 실행(0=전체)")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    if not CONFIG.has_openai_key:
        print("SKIP: .env의 PROXY_TOKEN이 없어 실제 LLM 호출을 할 수 없습니다.")
        return 0

    _isolate_data()
    from fixed.week_agent_registry import run_active_week_agent
    from student_parts.week04_retrieve_nanas_memory import build_week_agent

    build_week_agent()  # 동시 실행 전에 agent를 한 번만 빌드(빌드 레이스 방지)

    cases = CASES[: args.limit] if args.limit else CASES

    def run_one(case: dict) -> dict:
        result = run_active_week_agent(args.week, [{"role": "user", "content": case["prompt"]}])
        called, results = _called_tools_and_results(result.trace)
        expect = case["expect_tool"]
        if expect is None:  # control
            passed = not any(name in TARGET_TOOLS for name in called)
        else:
            passed = expect in called
        contract_ok = True
        if CONVERSATION in called:
            content = results.get(CONVERSATION)
            contract_ok = isinstance(content, dict) and CONTRACT_KEYS.issubset(content.keys())
        return {
            "category": case["category"],
            "expect_tool": expect,
            "called": called,
            "passed": passed,
            "contract_ok": contract_ok,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        outcomes = list(pool.map(run_one, cases))

    by_cat: dict[str, list[dict]] = {}
    for outcome in outcomes:
        by_cat.setdefault(outcome["category"], []).append(outcome)

    print(f"=== Golden 결과 (week{args.week}, {len(cases)}건) ===\n")
    total_pass = 0
    for category in sorted(by_cat):
        rows = by_cat[category]
        passed = sum(1 for r in rows if r["passed"])
        total_pass += passed
        print(f"[{category}] {passed}/{len(rows)} pass ({100.0 * passed / len(rows):.1f}%)")
        fails = [r for r in rows if not r["passed"]]
        if fails:
            if category == "control":
                wrong = Counter(t for r in fails for t in r["called"] if t in TARGET_TOOLS)
                print(f"    오호출된 target tool: {dict(wrong)}")
            else:
                miss = Counter(t for r in fails for t in (r["called"] or ["(tool 호출 없음)"]))
                print(f"    기대 tool 대신 호출된 것: {dict(miss)}")

    contract_fail = [r for r in outcomes if CONVERSATION in r["called"] and not r["contract_ok"]]
    print()
    print(f"conversation tool 호출 시 JSON 계약(hits/rows/context/rag_backend/sync) 위반: {len(contract_fail)}건")
    print(f"\n전체: {total_pass}/{len(cases)} pass ({100.0 * total_pass / len(cases):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
