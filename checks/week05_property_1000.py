"""Week 5 재작업 1000 케이스 (결정론적 속성 검증) — 5week_docs/WEEK05_TEST_PLAN_1000.md.

collect_member_schedules의 핵심 계약을 대량 검증한다:
  - 내 일정이 date_from~date_to(inclusive) 밖이면 결과 rows에 없어야 한다 (멘토 1차 수정 요청)
  - 결과 rows에 조회 범위 밖 date가 하나도 없어야 한다
  - 외부(MCP) rows는 그대로 보존, 내 일정 member_name은 "나", 모든 row 6키 유지

외부 MCP 경계는 monkeypatch로 대체(subprocess 없이 1000회 고속). 실제 MCP 통합은
checks/week05_contract_check.py가 담당. 임계값: 1000/1000 (100%, 하드 게이트).
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from student_parts import week05_load_kanas_past_conversations as w5

ROW_KEYS = {"member_name", "title", "date", "start_time", "end_time", "notes"}
CASES_DUMP = PACKAGE_ROOT / "checks" / "week05_cases_1000.jsonl"


def _d(base: str, delta: int = 0) -> str:
    y, m, dd = (int(x) for x in base.split("-"))
    return (date(y, m, dd) + timedelta(days=delta)).isoformat()


def _external_within_range(name: str, args: dict) -> dict:
    """MCP가 date_from~date_to로 걸러 반환하는 상황을 흉내 — 항상 범위 안 row 1건."""
    return {
        "ok": True,
        "rows": [
            {
                "member_name": "철수",
                "title": "외부 회의",
                "date": args.get("date_from") or "2026-07-07",
                "start_time": "10:00",
                "end_time": "11:00",
                "notes": None,
            }
        ],
        "schedule_summary": "",
    }


def _personal(sched_date: str | None, idx: int = 0) -> dict:
    return {
        "id": f"p_{idx}",
        "title": f"내 일정 {idx}",
        "date": sched_date,
        "start_time": "09:00",
        "end_time": "10:00",
        "attendees": [],
        "session_id": "prop_scope",
    }


def build_cases() -> list[dict]:
    cases: list[dict] = []

    # A. 날짜범위 필터 그리드 (40 날짜 × 20 범위 = 800)
    grid_dates = [_d("2026-06-01", i * 3) for i in range(40)]  # 6/1 ~ 약 9/28, 40개
    ranges = []
    for i in range(20):
        f = _d("2026-06-15", i * 4)
        t = _d(f, 9)  # 10일 폭
        ranges.append((f, t))
    for D in grid_dates:
        for (F, T) in ranges:
            cases.append({"group": "A", "personal": [D], "date_from": F, "date_to": T})

    # B. 다건 혼합 (120): 범위 안/밖 섞인 여러 내 일정
    for i in range(120):
        F = _d("2026-07-01", i % 10)
        T = _d(F, 7)
        inside = [_d(F, 0), _d(F, 3), _d(T, 0)]
        outside = [_d(F, -5), _d(T, 5), _d(F, -30)]
        personal = inside[: 1 + (i % 3)] + outside[: 1 + (i % 3)]
        cases.append({"group": "B", "personal": personal, "date_from": F, "date_to": T})

    # C. 경계값 (40): D == F, D == T, D == F-1, D == T+1
    for i in range(10):
        F = _d("2026-07-05", i)
        T = _d(F, 6)
        for D in (F, T, _d(F, -1), _d(T, 1)):
            cases.append({"group": "C", "personal": [D], "date_from": F, "date_to": T})

    # D. 인자-무시 트랩 (40): date_from만/ date_to만 무시하면 통과되는 함정
    for i in range(20):
        F = _d("2026-07-10", i % 5)
        T = _d(F, 5)
        # date_from 무시하면 통과: date_to 이내지만 date_from 이전
        cases.append({"group": "D", "personal": [_d(F, -3)], "date_from": F, "date_to": T})
        # date_to 무시하면 통과: date_from 이후지만 date_to 초과
        cases.append({"group": "D", "personal": [_d(T, 3)], "date_from": F, "date_to": T})

    return cases


def _in_range(d: str | None, f: str, t: str) -> bool:
    return d is not None and f <= d <= t


def run_case(case: dict) -> tuple[bool, str]:
    F, T = case["date_from"], case["date_to"]
    personal = [_personal(d, i) for i, d in enumerate(case["personal"])]
    result = w5._collect_member_schedules(member_names=["철수"], date_from=F, date_to=T, personal_schedules=personal)
    rows = result.get("rows", [])

    # 불변식 1: 모든 row가 6키
    if not all(ROW_KEYS.issubset(r.keys()) for r in rows):
        return False, "row 6키 누락"
    # 불변식 2: 범위 밖 date가 하나도 없어야 (핵심 계약)
    out = [r.get("date") for r in rows if not _in_range(r.get("date"), F, T)]
    if out:
        return False, f"범위 밖 date 섞임: {out}"
    # 불변식 3: 내 일정("나") — 범위 안인 것만 정확히 포함
    my_rows = [r for r in rows if r.get("member_name") == "나"]
    expected_my = sorted(d for d in case["personal"] if _in_range(d, F, T))
    got_my = sorted(r.get("date") for r in my_rows)
    if got_my != expected_my:
        return False, f"내 일정 불일치 expected={expected_my} got={got_my}"
    # 불변식 4: 외부(철수) 보존
    if not any(r.get("member_name") == "철수" for r in rows):
        return False, "외부 멤버 row 보존 안됨"
    # 불변식 5: schedule_summary 존재
    if "schedule_summary" not in result:
        return False, "schedule_summary 없음"
    return True, ""


def main() -> int:
    # 외부 MCP 경계 주입 (subprocess 없이)
    w5.call_external_tool_payload = _external_within_range

    cases = build_cases()
    with CASES_DUMP.open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    by_group: dict[str, list[bool]] = {}
    failures: list[str] = []
    for i, case in enumerate(cases):
        ok, reason = run_case(case)
        by_group.setdefault(case["group"], []).append(ok)
        if not ok and len(failures) < 15:
            failures.append(f"[{case['group']}] {case['date_from']}~{case['date_to']} personal={case['personal']} -> {reason}")

    total = len(cases)
    passed = sum(1 for g in by_group.values() for x in g if x)
    print(f"=== Week5 1000 property check ({total}건, 케이스 덤프: {CASES_DUMP.name}) ===\n")
    for g in sorted(by_group):
        p = sum(by_group[g])
        print(f"[{g}] {p}/{len(by_group[g])} pass")
    if failures:
        print("\n실패 예시(최대 15):")
        for f in failures:
            print("  -", f)
    print()
    print(f"전체: {passed}/{total} pass ({100.0 * passed / total:.1f}%)  임계값=100%")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
