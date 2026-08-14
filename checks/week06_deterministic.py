"""Week 6 결정론적 케이스 실행 — checks/week06_cases.py의 property + static 케이스만.

golden(kind=='golden')은 실제 agent 호출이 필요하므로 여기서 실행하지 않고 건너뛴다(배치용).
구현 전에는 스텁이라 실패하는 게 정상(spec-first). 구현 후 100%가 목표.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from checks.week06_cases import build_all
from student_parts import week06_kanamate_decides_schedule as w6
from student_parts.week04_retrieve_nanas_memory import week04_prompt_parts
from student_parts.week05_load_kanas_past_conversations import week05_prompt_parts

_ACCUM = {"week04": week04_prompt_parts, "week05": week05_prompt_parts}


def _text_of(item: str) -> str:
    if item.endswith("_prompt_parts"):
        return " ".join(getattr(w6, item)())
    if item == "supervisor_system_prompt":
        return w6.supervisor_system_prompt()
    return str(getattr(w6, item))  # description 상수


def run_static(case: dict) -> tuple[bool, str]:
    item = case["item"]
    a = case["assert"]
    if a == "nonempty":
        return (len(_text_of(item).strip()) > 0, "빈 문자열")
    if a == "contains":
        return (case["target"] in _text_of(item), f"'{case['target']}' 미포함")
    if a == "accumulates":
        parts = _ACCUM[case["target"]]()
        cur = getattr(w6, item)()
        return (all(p in cur for p in parts), f"{case['target']} 조각 누적 안됨")
    return (False, f"알수없는 assert {a}")


def run_find_common(case: dict) -> tuple[bool, str]:
    kwargs = dict(member_names=case["member_names"], date_from=case["date_from"], date_to=case["date_to"],
                  duration_minutes=case["duration_minutes"], busy_rows=case["busy_rows"],
                  candidate_slots=case["candidate_slots"])
    if case["item"] == "find_common_available_slots_dict":
        result = w6.find_common_available_slots_dict(**kwargs)
    else:
        result = json.loads(w6.find_common_available_slots.invoke(kwargs))
    if not isinstance(result, dict) or "candidate_slots" not in result:
        return (False, "candidate_slots 키 없음")
    kept = len(result.get("candidate_slots") or [])
    if kept != case["expect_kept"]:
        return (False, f"검증 후 후보수 {kept} != 기대 {case['expect_kept']}")
    if "나" not in (result.get("members") or []):
        return (False, "members에 '나' 없음")
    return (True, "")


def run_decide_final(case: dict) -> tuple[bool, str]:
    args = {k: case[k] for k in ("candidate_slots", "member_names", "date_from", "date_to") if k in case}
    for k in ("selected_index", "final_slot"):
        if k in case:
            args[k] = case[k]
    result = json.loads(w6.decide_final_slot.invoke(args))
    for key in ("final_slot", "reason", "candidates", "needs_agent_selection"):
        if key not in result:
            return (False, f"top-level '{key}' 없음")
    if result["needs_agent_selection"] != case["expect_needs"]:
        return (False, f"needs_agent_selection {result['needs_agent_selection']} != {case['expect_needs']}")
    if case["expect_final_not_null"] != (result["final_slot"] is not None):
        return (False, f"final_slot null 여부 불일치 ({result['final_slot']})")
    return (True, "")


def main() -> int:
    all_cases = build_all()
    grand_pass = grand_total = 0
    print("=== Week6 결정론적 케이스 실행 (golden 제외) ===\n")
    for item, cases in all_cases.items():
        det = [c for c in cases if c["kind"] in ("static", "property")]
        if not det:
            print(f"[{item}] 결정론적 0개 (golden 200개 — 배치 실행)")
            continue
        p = 0
        first_fail = ""
        for c in det:
            try:
                if c["kind"] == "static":
                    ok, reason = run_static(c)
                elif c["item"] in ("find_common_available_slots_dict", "find_common_available_slots"):
                    ok, reason = run_find_common(c)
                else:
                    ok, reason = run_decide_final(c)
            except Exception as exc:  # noqa: BLE001
                ok, reason = False, f"{type(exc).__name__}: {exc}"
            if ok:
                p += 1
            elif not first_fail:
                first_fail = reason
        grand_pass += p
        grand_total += len(det)
        tag = "OK" if p == len(det) else f"FAIL(예:{first_fail})"
        print(f"[{item}] {p}/{len(det)} pass  {tag}  (+golden {len(cases)-len(det)})")
    print(f"\n결정론적 전체: {grand_pass}/{grand_total} pass")
    print("(구현 전이면 실패가 정상 — spec-first. 구현 후 100% 목표)")
    return 0 if grand_pass == grand_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
