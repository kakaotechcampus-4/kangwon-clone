"""Week 5 golden tool-selection 측정 (실제 agent, Tier2).

외부 멤버 일정 관련 질문에서 agent가 Week 5 MCP wrapper tool을 고르는지, 그리고
내 일정/잡담 등 control 질문에서 Week 5 tool을 오호출하지 않는지 측정합니다.

데이터 격리: 실제 data/를 임시 폴더로 복사한 뒤 CONFIG 경로를 패치하고 나서 모듈을
로드합니다. 실제 data/는 변경되지 않습니다.

정량 임계값:
  - control 오호출(false positive) = 0건
  - external_people 카테고리 pass율 >= 70%

실행: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week05_golden.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from fixed.config import CONFIG

# 외부 멤버 조회용 read tool — external_people 케이스는 이 중 하나가 불려야 pass
WEEK5_READ_TOOLS = {
    "search_previous_conversations",
    "load_conversation_messages",
    "extract_schedules_from_history",
    "list_shared_schedules",
    "collect_member_schedules",
}
# read + write(추가과제) 전체 — control 케이스는 이 중 무엇도 불리면 오호출
WEEK5_TOOLS = WEEK5_READ_TOOLS | {"create_shared_schedule", "delete_shared_schedule"}

_TONES = ["{p}", "{p}?", "혹시 {p}", "{p} 좀 알려줘"]

# 외부 멤버(다른 사람) 일정/대화 → Week 5 MCP tool 중 하나가 호출돼야 함
_EXTERNAL_CORE = [
    "철수랑 영희 7월 일정 알려줘",
    "다른 팀원들 이번 달에 언제 바빠",
    "민준이랑 서연이 시간 되는 거 일정 좀 모아줘",
    "지훈이 예전 대화에서 일정 관련된 거 찾아줘",
    "하린이랑 철수 공유된 일정 보여줘",
    "팀원들 busy time 모아서 알려줘",
]

# 내 것/잡담 → Week 5 tool이 호출되면 오호출(false positive)
_CONTROL_CORE = [
    "내 일정 보여줘",
    "안녕 오늘 기분 어때",
    "나는 매운 걸 잘 못 먹어 기억해둬",
    "내가 저장한 할 일 검색해줘",
]


def _expand(core: list[str]) -> list[str]:
    return [t.format(p=b) for b in core for t in _TONES]


def build_cases() -> list[dict]:
    cases: list[dict] = []
    for p in _expand(_EXTERNAL_CORE):
        cases.append({"category": "external_people", "prompt": p})
    for p in _expand(_CONTROL_CORE):
        cases.append({"category": "control", "prompt": p})
    return cases


def _isolate_data() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="w5_golden_"))
    for src in (CONFIG.app_db_path, CONFIG.external_db_path):
        if Path(src).exists():
            shutil.copy2(src, tmp / Path(src).name)
    if Path(CONFIG.chroma_dir).exists():
        shutil.copytree(CONFIG.chroma_dir, tmp / "chroma")
    object.__setattr__(CONFIG, "app_db_path", tmp / Path(CONFIG.app_db_path).name)
    object.__setattr__(CONFIG, "external_db_path", tmp / Path(CONFIG.external_db_path).name)
    object.__setattr__(CONFIG, "chroma_dir", tmp / "chroma")
    return tmp


def _called(trace: dict) -> list[str]:
    events = trace.get("events", []) if isinstance(trace, dict) else []
    return [e.get("tool_name") for e in events if e.get("event") == "tool_call" and e.get("tool_name")]


def main() -> int:
    if not CONFIG.has_openai_key:
        print("SKIP: PROXY_TOKEN 없음")
        return 0

    _isolate_data()
    from fixed.week_agent_registry import run_active_week_agent
    from student_parts.week05_load_kanas_past_conversations import build_week_agent

    build_week_agent()
    cases = build_cases()

    def run_one(case: dict) -> dict:
        result = run_active_week_agent(5, [{"role": "user", "content": case["prompt"]}])
        called = _called(result.trace)
        w5_called = [t for t in called if t in WEEK5_TOOLS]
        if case["category"] == "external_people":
            passed = any(t in WEEK5_READ_TOOLS for t in called)
        else:
            passed = len(w5_called) == 0
        return {"category": case["category"], "called": called, "w5_called": w5_called, "passed": passed}

    with ThreadPoolExecutor(max_workers=5) as pool:
        outcomes = list(pool.map(run_one, cases))

    by_cat: dict[str, list[dict]] = {}
    for o in outcomes:
        by_cat.setdefault(o["category"], []).append(o)

    print(f"=== Week5 Golden ({len(cases)}건) ===\n")
    ext = by_cat.get("external_people", [])
    ctl = by_cat.get("control", [])
    ext_pass = sum(1 for r in ext if r["passed"])
    ctl_fp = sum(1 for r in ctl if not r["passed"])
    ext_pct = 100.0 * ext_pass / len(ext) if ext else 0.0

    print(f"[external_people] {ext_pass}/{len(ext)} pass ({ext_pct:.1f}%)")
    miss = Counter(t for r in ext if not r["passed"] for t in (r["called"] or ["(tool 호출 없음)"]))
    if miss:
        print(f"    Week5 tool 대신 호출/미호출: {dict(miss)}")
    print(f"[control] 오호출(false positive) {ctl_fp}/{len(ctl)}건")
    if ctl_fp:
        fp = Counter(t for r in ctl if not r["passed"] for t in r["w5_called"])
        print(f"    오호출된 Week5 tool: {dict(fp)}")

    threshold_ok = (ext_pct >= 70.0) and (ctl_fp == 0)
    print()
    print(f"임계값: external_people >= 70% AND control 오호출 0")
    print(f"결과: external={ext_pct:.1f}%, control 오호출={ctl_fp}건 -> {'통과' if threshold_ok else '미달'}")
    return 0 if threshold_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
