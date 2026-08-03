"""Week 5 계약 검증 (결정론적, 실제 MCP read-only).

메인+공통과제 wrapper tool이 MCP를 올바르게 호출하고 계약 필드를 반환하는지,
collect_member_schedules가 내 일정("나")과 외부 멤버 일정을 같은 구조로 합치는지 검증합니다.

- 외부 SQLite(data/kanana_external_people.sqlite3)는 읽기 전용 + seed 데이터라 부작용 없음.
- "나" 일정은 PERSONAL_SCHEDULES(인메모리, 현재 대화 scope)로만 심어 DB를 건드리지 않음.
- 정량 임계값: 전 항목 PASS(100%). 하나라도 실패하면 exit 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from fixed.session_scope import conversation_session_scope
from student_parts.week01_wake_up_nana import PERSONAL_SCHEDULES
from student_parts import week05_load_kanas_past_conversations as w5

MEMBER = "철수"
DATE_FROM = "2026-07-01"
DATE_TO = "2026-07-31"
ROW_KEYS = {"member_name", "title", "date", "start_time", "end_time", "notes"}


def _invoke(tool, args) -> dict:
    return json.loads(tool.invoke(args))


def main() -> int:
    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    # 1. search_previous_conversations
    try:
        d = _invoke(w5.search_previous_conversations, {"query": "일정", "member_names": [MEMBER], "limit": 5})
        rows = d.get("rows", [])
        check("1) search_previous_conversations: rows 존재", isinstance(rows, list) and len(rows) >= 1)
        check("1) rows에 conversation_id/member_name/content", bool(rows) and all(k in rows[0] for k in ("conversation_id", "member_name", "content")))
    except Exception as exc:  # noqa: BLE001
        check(f"1) search_previous_conversations 예외 없음 ({type(exc).__name__}: {exc})", False)

    # 2. load_conversation_messages (순서 보존)
    try:
        d = _invoke(w5.load_conversation_messages, {"conversation_id": "ext_cs"})
        rows = d.get("rows", [])
        check("2) load_conversation_messages: rows 존재", isinstance(rows, list) and len(rows) >= 1)
        check("2) rows에 sender/content/created_at", bool(rows) and all(k in rows[0] for k in ("sender", "content", "created_at")))
        created = [str(r.get("created_at") or "") for r in rows]
        check("2) created_at 오름차순(순서 보존)", created == sorted(created))
    except Exception as exc:  # noqa: BLE001
        check(f"2) load_conversation_messages 예외 없음 ({type(exc).__name__}: {exc})", False)

    # 3. extract_schedules_from_history
    try:
        d = _invoke(w5.extract_schedules_from_history, {"member_names": [MEMBER], "date_from": DATE_FROM, "date_to": DATE_TO})
        rows = d.get("rows", [])
        check("3) extract_schedules_from_history: rows + schedule_summary", isinstance(rows, list) and "schedule_summary" in d)
        check("3) rows 비어있지 않음(철수 7월 일정)", len(rows) >= 1)
        check("3) row 필드 구조", bool(rows) and ROW_KEYS.issubset(rows[0].keys()))
    except Exception as exc:  # noqa: BLE001
        check(f"3) extract_schedules_from_history 예외 없음 ({type(exc).__name__}: {exc})", False)

    # 4. list_shared_schedules
    try:
        d = _invoke(w5.list_shared_schedules, {})
        rows = d.get("rows", [])
        check("4) list_shared_schedules: rows + schedule_summary 유지", isinstance(rows, list) and len(rows) >= 1 and "schedule_summary" in d)
    except Exception as exc:  # noqa: BLE001
        check(f"4) list_shared_schedules 예외 없음 ({type(exc).__name__}: {exc})", False)

    # 5. collect_member_schedules ("나" + 외부 멤버 같은 구조로 병합)
    scope = "w5_contract_scope"
    seeded = {"id": "personal_w5test", "title": "내 집중작업", "date": "2026-07-09", "start_time": "09:00", "end_time": "10:00", "attendees": [], "session_id": scope}
    PERSONAL_SCHEDULES.append(seeded)
    try:
        with conversation_session_scope(scope):
            d = _invoke(w5.collect_member_schedules, {"member_names": [MEMBER], "date_from": DATE_FROM, "date_to": DATE_TO})
        rows = d.get("rows", [])
        members = {r.get("member_name") for r in rows}
        check("5) collect_member_schedules: rows + schedule_summary", isinstance(rows, list) and "schedule_summary" in d and bool(d.get("schedule_summary")))
        check("5) '나' 일정 포함", "나" in members)
        check("5) 외부 멤버(철수) 일정 포함", MEMBER in members)
        check("5) 모든 row 동일 구조", bool(rows) and all(ROW_KEYS.issubset(r.keys()) for r in rows))
    except Exception as exc:  # noqa: BLE001
        check(f"5) collect_member_schedules 예외 없음 ({type(exc).__name__}: {exc})", False)
    finally:
        if seeded in PERSONAL_SCHEDULES:
            PERSONAL_SCHEDULES.remove(seeded)

    # 6. _personal_schedules_for_current_scope: scope 필터
    scope_a, scope_b = "w5_scope_a", "w5_scope_b"
    s_a = {"id": "p_a", "title": "A일정", "date": "2026-07-10", "start_time": "11:00", "end_time": "12:00", "attendees": [], "session_id": scope_a}
    s_b = {"id": "p_b", "title": "B일정", "date": "2026-07-10", "start_time": "13:00", "end_time": "14:00", "attendees": [], "session_id": scope_b}
    PERSONAL_SCHEDULES.extend([s_a, s_b])
    try:
        with conversation_session_scope(scope_a):
            got = w5._personal_schedules_for_current_scope()
        titles = {r.get("title") for r in got}
        check("6) 현재 scope(A) 임시 일정 포함", "A일정" in titles)
        check("6) 다른 scope(B) 임시 일정 제외", "B일정" not in titles)
    except Exception as exc:  # noqa: BLE001
        check(f"6) _personal_schedules_for_current_scope 예외 없음 ({type(exc).__name__}: {exc})", False)
    finally:
        for s in (s_a, s_b):
            if s in PERSONAL_SCHEDULES:
                PERSONAL_SCHEDULES.remove(s)

    # 7. (멘토 1차 수정요청) 실제 MCP — 조회 범위 밖 내 일정이 rows에 섞이면 안 됨
    scope_r = "w5_range_scope"
    aug = {"id": "p_aug", "title": "8월 개인 미팅", "date": "2026-08-20", "start_time": "14:00", "end_time": "15:00", "attendees": [], "session_id": scope_r}
    PERSONAL_SCHEDULES.append(aug)
    try:
        with conversation_session_scope(scope_r):
            d = _invoke(w5.collect_member_schedules, {"member_names": [MEMBER], "date_from": "2026-07-07", "date_to": "2026-07-16"})
        rows = d.get("rows", [])
        out_of_range = [r for r in rows if not (r.get("date") and "2026-07-07" <= r["date"] <= "2026-07-16")]
        check("7) 조회 범위(7/7~7/16) 밖 일정이 rows에 없음", out_of_range == [])
        check("7) 8월 개인 일정이 rows에서 제외됨", all(r.get("date") != "2026-08-20" for r in rows))
    except Exception as exc:  # noqa: BLE001
        check(f"7) 범위 밖 필터 예외 없음 ({type(exc).__name__}: {exc})", False)
    finally:
        if aug in PERSONAL_SCHEDULES:
            PERSONAL_SCHEDULES.remove(aug)

    # 8. (추가과제) create/delete_shared_schedule round-trip — 만든 row만 건드리고 정리
    unique_id = "sharedtest_w5contract"
    w5.delete_shared_schedule.invoke({"schedule_id": unique_id})  # 사전 정리
    try:
        created = _invoke(w5.create_shared_schedule, {"member_name": "테스트원", "title": "계약검증용", "date": "2026-07-11", "start_time": "10:00", "end_time": "11:00", "schedule_id": unique_id})
        check("8) create_shared_schedule: shared_schedule 반환 + schedule_id 보존", created.get("shared_schedule", {}).get("schedule_id") == unique_id)
        listed = _invoke(w5.list_shared_schedules, {"member_names": ["테스트원"]})
        check("8) 등록한 공유 일정이 list에 나타남", any(r.get("schedule_id") == unique_id for r in listed.get("rows", [])))
        deleted = _invoke(w5.delete_shared_schedule, {"schedule_id": unique_id})
        check("8) delete_shared_schedule: deleted_count>=1", deleted.get("deleted_count", 0) >= 1)
        listed2 = _invoke(w5.list_shared_schedules, {"member_names": ["테스트원"]})
        check("8) 삭제 후 list에서 사라짐", all(r.get("schedule_id") != unique_id for r in listed2.get("rows", [])))
    except Exception as exc:  # noqa: BLE001
        check(f"8) create/delete round-trip 예외 없음 ({type(exc).__name__}: {exc})", False)
    finally:
        w5.delete_shared_schedule.invoke({"schedule_id": unique_id})  # 사후 정리

    print()
    total = len(failures)
    if total:
        print(f"FAILED: {total}개 체크 실패 -> {failures}")
        return 1
    print("ALL CHECKS PASSED (100%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
