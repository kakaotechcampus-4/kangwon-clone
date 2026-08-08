"""Week 6 위임 실험 harness — Layer 2 (반자동, LLM 실제 호출).

이것은 pytest 테스트가 아니다. LLM 을 부르므로 비결정적이고 매 실행 결과가 달라
CI 에 넣지 않는다. 파일명에 test_ 접두어를 안 붙인 이유가 그거다.
(Layer 1 = tests/test_week06_supervisor.py — LLM 없이 위임 wrapper 계약만 본다)

무엇을 재는가
  Layer 1 이 "wrapper 가 계약대로 만드는가"를 봤다면, 여기서는
  "세 개의 system prompt 가 실제로 위임 판단을 바꾸는가"를 통과율로 잰다.
  케이스는 6주차 prompt 가 지시한 것을 따라간다.
    ① 개인 업무는 nana_agent, 남의 일정·대화는 kana_agent (위임 대상)
    ② 한 사람만 물어도 남의 일정이면 collect_member_schedules (Kana 는 누적이 없어 다시 써야 했다)
    ③ 조율 요청에는 저장하지 않는다 (앞 주차의 "일정 요청은 저장한다"가 덮는 지점)
    ④ 저장을 분명히 요청하면 조율 뒤 저장까지 간다

5주차 harness 와 판정 방식이 다른 점
  5주차는 하나의 agent trace 만 봤다. 6주차는 계층이 둘이라 두 군데를 본다.
    - supervisor 층: 어느 wrapper 가 불렸나 (nana_agent / kana_agent)
    - 하위 층: 그 wrapper 가 돌려준 inner_tool_names
  week06 의 extract_langchain_trace 가 두 값을 모두 정리해주므로 그걸 그대로 읽는다.
  (supervisor_selected_agent / inner_tool_names / final_slot_payload)

  ③ 을 통과율로 재는 이유:
    구현 중에 prompt 를 세 번 고쳤는데 run 마다 결과가 갈렸다. 단정하는 pytest 로
    만들면 통과했다 실패했다 하는 테스트가 되므로, 비율로 남기는 게 맞다고 봤다.
    "몇 번 중 몇 번" 이 곧 이 prompt 를 신뢰할 수 있는 정도다.

격리 (실 DB 오염 방지)
  5주차 harness 와 같은 방식이다. 이번엔 더 중요하다 —
  ③④ 케이스는 실제로 일정을 저장하고, ③ 이 실패하는 것 자체가 저장이라서
  실 DB 로 돌리면 실패할 때마다 쓰레기 일정이 쌓인다. (실제로 그렇게 14건을 남겼다)
    - 앱 DB: CONFIG.app_db_path 를 임시 파일로 replace 한 뒤 runtime 을 import 한다
      (import 시점에 경로가 고정되므로 지연 import).
    - 외부 DB: 실 파일을 임시 디렉터리로 복사하고 KANANA_EXTERNAL_DB_PATH 로 갈아끼운다.
      seed(2026-07-07~17, 멤버 6명)가 기대값의 근거라서 빈 DB 는 쓸 수 없다.

전제
  외부 seed 일정은 2026-07-07~17 이다. 조율 케이스의 날짜를 이 범위 근처로 둔 이유는
  상대방 일정이 하나라도 있어야 "겹치지 않는 시간을 골랐나"가 의미를 갖기 때문이다.
  추가과제(find_common_available_slots / decide_final_slot)를 아직 구현하지 않았으므로
  final_slot 은 관찰만 하고 통과 판정에 넣지 않는다.

실행:
  uv run python tests/manual_week06_delegation.py --runs 3
  uv run python tests/manual_week06_delegation.py --case D3 --runs 5
"""

import argparse
import dataclasses
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

# python tests/... 직접 실행 시 프로젝트 루트가 sys.path 에 없어 fixed/ 를 못 찾는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# 앱 DB 에 심어 둘 내 일정. 빈 DB 로 조율을 시키면 내 바쁜 시간이 없어서
# "겹치지 않는 시간을 골랐나"를 볼 수 없다.
SEEDED_MY_SCHEDULE = {
    "kind": "personal_schedule",
    "title": "합성 내 일정",
    "date": "2026-07-14",
    "start_time": "09:00",
    "end_time": "10:00",
}

# 저장이 일어났다는 증거가 되는 tool. ③ 케이스에서 이게 보이면 실패다.
WRITE_TOOLS = {
    "personal_create_schedule",
    "save_structured_request",
    "create_shared_schedule",
}

# 남의 일정을 볼 때 써야 하는 tool 과, 대신 새기 쉬운 tool
MEMBER_SCHEDULE_TOOL = "collect_member_schedules"
SHARED_ONLY_TOOL = "list_shared_schedules"


# --- trace 읽기 -------------------------------------------------------------


class Run:
    """한 번의 supervisor 실행에서 판정에 필요한 것만 꺼내 둔다."""

    def __init__(self, answer: str, trace: dict[str, Any]) -> None:
        self.answer = answer
        self.selected = trace.get("supervisor_selected_agent")
        self.inner: list[str] = list(trace.get("inner_tool_names") or [])
        self.final_slot_payload = trace.get("final_slot_payload") or {}
        # supervisor 층에서 어떤 wrapper 가 몇 번 불렸는지 — 위임을 두 번 했는지 보려면 필요하다.
        self.delegations: list[str] = []
        for event in trace.get("events", []):
            if not isinstance(event, dict):
                continue
            if event.get("event") == "tool_call" and event.get("tool_name") in {"nana_agent", "kana_agent"}:
                self.delegations.append(event["tool_name"])

    @property
    def writes(self) -> list[str]:
        return [name for name in self.inner if name in WRITE_TOOLS]

    def repr_flow(self) -> str:
        delegated = ">".join(self.delegations) if self.delegations else "(위임 없음)"
        inner = "|".join(self.inner) if self.inner else "(none)"
        return f"{delegated} :: {inner}"


# --- 케이스별 판정 ----------------------------------------------------------
# 반환은 (통과, 메모). 통과가 None 이면 집계에서 빼고 메모만 남긴다 — 관찰용이다.

Verdict = tuple[bool | None, str]


def judge_personal(run: Run) -> Verdict:
    """① 개인 업무는 nana_agent 로 가고 개인 일정 조회 tool 이 불린다.

    과제 검증 방법에 명시된 항목이다(가이드 123행).
    """

    if run.selected != "nana_agent":
        return False, f"nana_agent 가 아니라 {run.selected} 로 갔다"
    if "personal_list_saved_schedules" not in run.inner:
        return False, f"개인 일정 조회 tool 이 없다: {run.inner}"
    return True, ""


def judge_member_schedule(run: Run) -> Verdict:
    """② 한 사람만 물어도 남의 일정이면 collect_member_schedules 로 조회한다.

    list_shared_schedules 로 가면 공유 저장소에 등록된 row 만 봐서
    대화에서 뽑은 일정이 빠진다. 실제로 "일정 없음" 답이 나왔던 케이스다.
    """

    if run.selected != "kana_agent":
        return False, f"kana_agent 가 아니라 {run.selected} 로 갔다"
    if MEMBER_SCHEDULE_TOOL in run.inner:
        return True, ""
    if SHARED_ONLY_TOOL in run.inner:
        return False, f"{SHARED_ONLY_TOOL} 로 샜다 (등록된 row 만 봐서 대화 일정이 빠진다)"
    return False, f"멤버 일정 조회 tool 이 없다: {run.inner}"


def judge_conversation_search(run: Run) -> Verdict:
    """① 남의 예전 대화는 kana_agent 의 search_previous_conversations 로."""

    if run.selected != "kana_agent":
        return False, f"kana_agent 가 아니라 {run.selected} 로 갔다"
    if "search_previous_conversations" not in run.inner:
        return False, f"대화 검색 tool 이 없다: {run.inner}"
    return True, ""


def judge_no_write_on_coordination(run: Run) -> Verdict:
    """③ 조율만 요청했으면 저장하지 않는다.

    구현 중에 가장 안 잡힌 항목이다. 앞 주차의 "일정 요청을 받으면 저장한다"가
    6주차 지시를 덮는다. prompt 를 세 번 고쳤고 그래도 run 마다 갈렸다.
    """

    writes = run.writes
    if writes:
        return False, f"저장이 일어났다: {writes} (위임 흐름 {'>'.join(run.delegations)})"
    if run.selected != "kana_agent":
        return False, f"조율인데 {run.selected} 로 갔다"
    return True, ""


def judge_write_on_request(run: Run) -> Verdict:
    """④ 저장을 분명히 요청하면 조율한 뒤 저장까지 간다.

    ③ 과 짝이다. ③ 만 보면 "아무것도 저장 안 하는 prompt" 도 만점이 나온다.
    """

    if not run.writes:
        return False, f"저장 요청인데 저장 tool 이 없다: {run.inner}"
    if MEMBER_SCHEDULE_TOOL not in run.inner:
        return False, f"조율 없이 바로 저장했다: {run.inner}"
    return True, ""


def observe_time_unspecified(run: Run) -> Verdict:
    """관찰용. 참석자는 있는데 시간이 안 정해진 요청은 어디로 가는가.

    1차 리뷰에서 받은 질문이다. 지금 경계는 "참석자가 있어도 저장은 Nana 일"인데,
    이 입력에는 저장할 시간 자체가 없다. 어느 쪽이 맞는지 prompt 에 안 써뒀으므로
    단정하지 않고 관측만 한다. 저장이 일어나면 그게 제일 위험한 결과다 —
    시간을 지어내서 저장했다는 뜻이기 때문이다.
    """

    writes = run.writes
    if writes:
        return None, f"⚠ 시간이 없는데 저장했다: {writes} — 어떤 시간으로 저장했는지 답변 확인 필요"
    return None, f"{run.selected} 가 받고 저장 안 함 ({'|'.join(run.inner) or 'tool 없음'})"


def observe_final_slot(run: Run) -> Verdict:
    """관찰용. 추가과제 미구현 상태에서 최종 시간이 어떻게 나오는지만 본다."""

    slot = run.final_slot_payload.get("final_slot")
    if slot:
        return None, f"final_slot={slot}"
    if "decide_final_slot" in run.inner:
        return None, "decide_final_slot 은 불렸지만 확정 안 됨"
    return None, f"추가과제 미구현 — 답변으로만 시간 제시: {run.answer[:60]}"


# --- 케이스 ----------------------------------------------------------------


@dataclasses.dataclass
class Case:
    case_id: str
    group: str
    question: str
    judge: Callable[[Run], Verdict]


CASES: list[Case] = [
    Case("D1", "위임", "내가 저장한 일정 알려줘", judge_personal),
    Case("D2", "위임", "민준이 7월 14일에 무슨 일정 있어?", judge_member_schedule),
    Case("D3", "위임", "시우가 예전에 발표 얘기한 대화 찾아줘", judge_conversation_search),
    Case("D4", "저장경계", "민준이랑 7월 14일부터 16일 사이에 1시간 회의 시간 맞춰줘", judge_no_write_on_coordination),
    Case("D5", "저장경계", "민준이랑 7월 15일 오후에 1시간 회의 잡고 내 일정에 등록해줘", judge_write_on_request),
    Case("D6", "관찰", "하린이랑 7월 16일에 2시간 회의 시간 찾아줘", observe_final_slot),
    Case("D7", "관찰", "철수랑 다음 주에 회의 잡아줘", observe_time_unspecified),
]


def build_runtime() -> Any:
    """임시 앱 DB + 외부 DB 복사본으로 갈아끼운 뒤 week6 runtime 을 만든다.

    CONFIG replace 가 import 보다 먼저여야 하므로 지연 import 한다.
    """

    import fixed.config as config_module

    tmp_dir = Path(tempfile.mkdtemp(prefix="week06_delegation_"))

    source_db = Path(config_module.CONFIG.external_db_path)
    if not source_db.exists():
        print(f"❌ 외부 DB 를 찾을 수 없습니다: {source_db}", file=sys.stderr)
        print("   ./run.sh 를 한 번 실행해 seed 를 만든 뒤 다시 시도하세요.", file=sys.stderr)
        sys.exit(1)
    external_copy = tmp_dir / "external_copy.sqlite3"
    shutil.copy2(source_db, external_copy)
    os.environ["KANANA_EXTERNAL_DB_PATH"] = str(external_copy)

    test_config = dataclasses.replace(
        config_module.CONFIG,
        app_db_path=tmp_dir / "empty_app.sqlite3",
        external_db_path=external_copy,
        active_week=6,
    )
    config_module.CONFIG = test_config

    if not test_config.has_openai_key:
        print("❌ PROXY_TOKEN이 없습니다. .env에 키를 넣고 다시 실행하세요.", file=sys.stderr)
        sys.exit(1)

    from fixed.app_store import AppSQLiteStore

    AppSQLiteStore(test_config.app_db_path).save_structured_request(dict(SEEDED_MY_SCHEDULE))

    print(f"# 격리: 앱 DB={test_config.app_db_path.name} · 외부 DB 복사본={external_copy}")
    print(f"# 심어둔 내 일정: {SEEDED_MY_SCHEDULE['date']} {SEEDED_MY_SCHEDULE['start_time']} {SEEDED_MY_SCHEDULE['title']}")

    from fixed.agent_runtime import AgentRuntime

    return AgentRuntime(active_week=6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="케이스당 반복 횟수 (기본 3)")
    parser.add_argument("--case", action="append", help="특정 case_id 만 실행 (여러 번 지정 가능)")
    options = parser.parse_args()

    cases = [case for case in CASES if not options.case or case.case_id in options.case]
    if not cases:
        print(f"❌ 해당하는 케이스가 없습니다: {options.case}", file=sys.stderr)
        sys.exit(1)

    runtime = build_runtime()
    print(f"# Week 6 위임 — 케이스당 {options.runs}회, 새 대화")
    print("# 표기: (supervisor 위임)>(추가 위임) :: (하위 tool 호출)")
    print()

    tally: dict[str, list[int]] = {}
    for case in cases:
        tally[case.case_id] = [0, 0]
        print(f"── {case.case_id} [{case.group}] {case.question}")
        for run_index in range(1, options.runs + 1):
            result = runtime.run_agent(case.question, conversation_id=None)
            run = Run(result.answer, result.trace)
            passed, note = case.judge(run)

            if passed is not None:
                tally[case.case_id][1] += 1
                if passed:
                    tally[case.case_id][0] += 1
            mark = {True: "Y", False: "N", None: "-"}[passed]
            print(f"   {run_index} {mark}  {run.repr_flow()}")
            if note:
                print(f"      {note}")
        print()

    print("## 통과율 (관찰 케이스는 제외)")
    for case in cases:
        passes, total = tally[case.case_id]
        if not total:
            print(f"  {case.case_id}: 관찰만 (위 메모 참고)")
            continue
        print(f"  {case.case_id}: {passes}/{total} = {100 * passes / total:.0f}%")


if __name__ == "__main__":
    main()
