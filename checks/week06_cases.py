"""Week 6 테스트 케이스 생성기 — 11개 구현 항목 × 200개 = 2200개 (미리 준비).

항목 성격이 달라 200개 구성이 다르다(모두 '만족 가능한' 케이스만, 패딩 가짜토큰 없음):
  - 결정론적 property (9,10,11): 날짜/시간/busy_rows/candidate 조합 200개 — 지금 실행 가능(무료)
  - 정적 구조 (1~4,7,8): 만족 가능한 구조 검사 + 그 프롬프트/description이 '가능케 해야 할'
    golden 발화 케이스로 200 채움
  - golden 행동 (5,6): 실제 agent 호출 발화 케이스 200개 — 배치 실행용으로 준비만

덤프: checks/week06_cases/<item>.jsonl (11파일, 2200줄).
결정론적 실행: checks/week06_deterministic.py.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = PACKAGE_ROOT / "checks" / "week06_cases"

PER_ITEM = 200
ITEMS = [
    "week06_prompt_parts", "nana_prompt_parts", "kana_prompt_parts", "supervisor_system_prompt",
    "nana_agent", "kana_agent",
    "FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION", "DECIDE_FINAL_SLOT_DESCRIPTION",
    "find_common_available_slots_dict", "find_common_available_slots", "decide_final_slot",
]

MEMBERS = ["철수", "영희", "민준", "서연", "지훈", "하린"]


def _d(base: str, delta: int = 0) -> str:
    y, m, dd = (int(x) for x in base.split("-"))
    return (date(y, m, dd) + timedelta(days=delta)).isoformat()


# ---------- golden 발화 풀 (만족 가능, 배치 실행용) ----------

def _nana_utterances(n: int) -> list[str]:
    cores = [
        "내 일정 보여줘", "내일 오후 3시에 개인 코칭 잡아줘", "내 할 일 목록 알려줘",
        "내가 저장한 참고자료 찾아줘", "내 취향 기억해둬: 나는 아침형이야", "이번 주 내 일정 뭐 있어",
        "내 알림 저장한 거 있어", "저번에 내가 뭐라고 했는지 찾아줘", "내 개인 일정 하나 지워줘",
        "내 저장된 회의 일정 검색해줘",
    ]
    tones = ["{p}", "{p} 좀", "혹시 {p}?", "{p}, 부탁해"]
    out = [t.format(p=c) for c in cores for t in tones]
    return (out * ((n // len(out)) + 1))[:n]


def _kana_utterances(n: int) -> list[str]:
    tmpl = [
        "{a}랑 {b} 7월 일정 알려줘", "{a}랑 {b} 공통으로 시간 되는 회의 시간 잡아줘",
        "팀원들 이번 달 언제 바빠", "{a} 예전 대화에서 일정 찾아줘", "공유 일정 목록 보여줘",
        "{a}랑 {b}랑 나까지 다 되는 시간 찾아서 회의 잡아줘", "{a} busy time 뽑아줘",
    ]
    out = []
    for i in range(n):
        a, b = MEMBERS[i % len(MEMBERS)], MEMBERS[(i + 1) % len(MEMBERS)]
        out.append(tmpl[i % len(tmpl)].format(a=a, b=b))
    return out


def _group_schedule_utterances(n: int) -> list[str]:
    out = []
    for i in range(n):
        a, b = MEMBERS[i % len(MEMBERS)], MEMBERS[(i + 2) % len(MEMBERS)]
        f = _d("2026-07-06", i % 12)
        t = _d(f, 8)
        out.append(f"{a}랑 {b}랑 나까지 {f}~{t} 사이에 회의 시간 정해줘")
    return out


# ---------- 항목별 200 케이스 ----------

def gen_prompt_item(item: str, accumulate: str | None, must_contain: list[str], routing_pool) -> list[dict]:
    cases: list[dict] = []
    cases.append({"item": item, "kind": "static", "assert": "nonempty"})
    if accumulate:
        cases.append({"item": item, "kind": "static", "assert": "accumulates", "target": accumulate})
    for tok in must_contain:
        cases.append({"item": item, "kind": "static", "assert": "contains", "target": tok})
    # 나머지는 이 프롬프트가 '가능케 해야 할' golden 발화로 채움(만족 가능, 배치 실행)
    remaining = PER_ITEM - len(cases)
    utter = routing_pool(remaining)
    for u in utter:
        cases.append({"item": item, "kind": "golden", "prompt": u})
    return cases[:PER_ITEM]


def gen_description_item(item: str, must_contain: list[str]) -> list[dict]:
    cases: list[dict] = [{"item": item, "kind": "static", "assert": "nonempty"}]
    for tok in must_contain:
        cases.append({"item": item, "kind": "static", "assert": "contains", "target": tok})
    remaining = PER_ITEM - len(cases)
    for u in _group_schedule_utterances(remaining):
        cases.append({"item": item, "kind": "golden", "prompt": u})
    return cases[:PER_ITEM]


def gen_agent_item(item: str, pool, expect_keys: list[str]) -> list[dict]:
    # 200개 golden 발화 (실제 agent 호출로 계약키/행동 검증) — 배치 실행 준비
    cases = []
    for u in pool(PER_ITEM):
        cases.append({"item": item, "kind": "golden", "prompt": u, "expect_keys": expect_keys})
    return cases[:PER_ITEM]


def gen_find_common_cases(item: str) -> list[dict]:
    """busy_rows/candidate_slots를 명시로 넘겨(MCP 불필요) 후보 필터 검증 200개."""
    cases: list[dict] = []
    base_from = "2026-07-06"
    for i in range(PER_ITEM):
        F = _d(base_from, i % 10)
        T = _d(F, 6)
        day = _d(F, i % 7)  # 범위 안 어떤 날
        # busy: 10:00-11:00 on `day`
        busy = [{"member_name": "철수", "date": day, "start_time": "10:00", "end_time": "11:00", "notes": None}]
        variant = i % 5
        if variant == 0:      # 겹치는 후보 → 제외돼야
            cand = [{"date": day, "start_time": "10:30", "end_time": "11:30", "duration_minutes": 60, "reason": "겹침"}]
            expect_kept = 0
        elif variant == 1:    # 안 겹치는 유효 후보 → 유지
            cand = [{"date": day, "start_time": "14:00", "end_time": "15:00", "duration_minutes": 60, "reason": "ok"}]
            expect_kept = 1
        elif variant == 2:    # 업무시간 밖(08:00) → 제외
            cand = [{"date": day, "start_time": "08:00", "end_time": "09:00", "duration_minutes": 60, "reason": "이른시간"}]
            expect_kept = 0
        elif variant == 3:    # 날짜 범위 밖 → 제외
            cand = [{"date": _d(T, 3), "start_time": "14:00", "end_time": "15:00", "duration_minutes": 60, "reason": "범위밖"}]
            expect_kept = 0
        else:                 # 너무 짧음(15분 < 60 요청) → 제외
            cand = [{"date": day, "start_time": "14:00", "end_time": "14:15", "duration_minutes": 15, "reason": "짧음"}]
            expect_kept = 0
        cases.append({
            "item": item, "kind": "property",
            "member_names": ["철수", "영희"], "date_from": F, "date_to": T,
            "duration_minutes": 60, "busy_rows": busy, "candidate_slots": cand,
            "expect_kept": expect_kept,
        })
    return cases


def gen_decide_final_cases(item: str) -> list[dict]:
    cases: list[dict] = []
    for i in range(PER_ITEM):
        F = _d("2026-07-06", i % 10)
        n_cand = i % 4  # 0..3 후보
        cands = [{"date": _d(F, k), "start_time": "14:00", "end_time": "15:00", "duration_minutes": 60, "reason": f"c{k}"} for k in range(n_cand)]
        variant = i % 4
        case = {"item": item, "kind": "property", "candidate_slots": cands, "member_names": ["철수"], "date_from": F, "date_to": _d(F, 6)}
        if variant == 0 and n_cand > 0:      # 유효 selected_index → final 확정
            case.update({"selected_index": 0, "expect_needs": False, "expect_final_not_null": True})
        elif variant == 1:                    # 아무 선택 없음 → 보류
            case.update({"expect_needs": True, "expect_final_not_null": False})
        elif variant == 2:                    # 범위 밖 index → 보류
            case.update({"selected_index": 99, "expect_needs": True, "expect_final_not_null": False})
        else:                                 # final_slot 직접 지정 → 확정
            case.update({"final_slot": f"{F} 14:00-15:00", "expect_needs": False, "expect_final_not_null": True})
        cases.append(case)
    return cases


def build_all() -> dict[str, list[dict]]:
    # week05/week04 프롬프트 조각을 accumulate 검증용으로 사용
    from student_parts.week05_load_kanas_past_conversations import week05_prompt_parts
    all_cases: dict[str, list[dict]] = {}
    all_cases["week06_prompt_parts"] = gen_prompt_item(
        "week06_prompt_parts", accumulate="week05",
        must_contain=["nana_agent", "kana_agent"], routing_pool=lambda n: (_nana_utterances(n // 2) + _kana_utterances(n - n // 2)))
    all_cases["nana_prompt_parts"] = gen_prompt_item(
        "nana_prompt_parts", accumulate="week04", must_contain=["Nana"], routing_pool=_nana_utterances)
    all_cases["kana_prompt_parts"] = gen_prompt_item(
        "kana_prompt_parts", accumulate=None,
        must_contain=["Kana", "collect_member_schedules", "extract_schedules_from_history"], routing_pool=_kana_utterances)
    all_cases["supervisor_system_prompt"] = gen_prompt_item(
        "supervisor_system_prompt", accumulate=None, must_contain=["nana_agent", "kana_agent"],
        routing_pool=lambda n: (_nana_utterances(n // 2) + _kana_utterances(n - n // 2)))
    all_cases["nana_agent"] = gen_agent_item("nana_agent", _nana_utterances, ["answer", "trace", "inner_tool_names"])
    all_cases["kana_agent"] = gen_agent_item("kana_agent", _kana_utterances, ["answer", "trace", "inner_tool_names", "final_slot_payload"])
    all_cases["FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION"] = gen_description_item(
        "FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION", ["candidate_slots", "busy_rows", "YYYY-MM-DD", "HH:MM", "decide_final_slot"])
    all_cases["DECIDE_FINAL_SLOT_DESCRIPTION"] = gen_description_item(
        "DECIDE_FINAL_SLOT_DESCRIPTION", ["final_slot", "needs_agent_selection", "selected_index"])
    all_cases["find_common_available_slots_dict"] = gen_find_common_cases("find_common_available_slots_dict")
    all_cases["find_common_available_slots"] = gen_find_common_cases("find_common_available_slots")
    all_cases["decide_final_slot"] = gen_decide_final_cases("decide_final_slot")
    return all_cases


def main() -> int:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    all_cases = build_all()
    total = 0
    print(f"=== Week6 케이스 생성 ({len(all_cases)}개 항목 × {PER_ITEM}) ===")
    for item, cases in all_cases.items():
        path = CASES_DIR / f"{item}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for c in cases:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        kinds = {}
        for c in cases:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
        total += len(cases)
        print(f"  {item}: {len(cases)}개 {kinds} -> {path.name}")
    print(f"\n총 {total}개 케이스 생성 (checks/week06_cases/)")
    return 0


if __name__ == "__main__":
    import sys
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))
    raise SystemExit(main())
