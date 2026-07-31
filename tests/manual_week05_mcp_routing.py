"""Week 5 MCP routing 실험 harness — Layer 2 (반자동, LLM 실제 호출).

이것은 pytest 테스트가 아니다. LLM을 부르므로 비결정적이고 매 실행 결과가 달라
CI에 넣지 않는다. 파일명에 test_ 접두어를 안 붙인 이유가 그거다.
(Layer 1 = tests/test_week05_mcp_tools.py — LLM 없이 계약만 본다)

무엇을 재는가
  Layer 1이 "wrapper가 손대지 않고 넘기는가"를 봤다면, 여기서는
  "week05_prompt_parts()가 실제로 LLM 행동을 바꾸는가"를 통과율로 잰다.
  5주차 프롬프트가 지시한 게 세 가지라 케이스도 그걸 따라간다.
    ① 내 저장소와 남의 저장소를 안 섞는다 + member_names에 "나"를 안 넣는다
    ② search 의 query 는 짧은 핵심 명사로 넣는다
    ③ conversation_id 는 검색 결과에서 가져온다 (지어내지 않는다)

4주차 harness와 판정 방식이 다른 점
  4주차는 "조회 tool 이름이 trace에 나왔나"만 봤다. 5주차는 그걸론 부족하다.
  member_names에 "나"가 들어갔는지는 이름이 아니라 인자를 봐야 나오고,
  검색어를 잘 골랐는지는 인자 길이를 재는 것보다 결과 rows가 비었는지로 보는 게 정확하다.
  그래서 trace의 arguments 와 tool_result content 를 같이 읽는다.
  (fixed/langchain_trace.py: {"event":"tool_call","tool_name","arguments"} /
                             {"event":"tool_result","tool_name","content"(파싱된 dict)})

  검색어 판정을 결과로 하는 이유:
    "짧은 명사인가"를 문자열 길이나 공백 수로 재면 자꾸 예외가 생긴다.
    LIKE '%query%' 대조라서 검색어가 문장이면 반드시 0건이 된다.
    즉 rows가 비었는지가 검색어 품질의 직접적인 결과다. 사람 판단이 안 낀다.

격리 (실 DB 오염 방지)
  - 앱 DB: CONFIG.app_db_path 를 임시 파일로 replace 한 뒤 runtime 을 import 한다
    (import 시점에 경로가 고정되므로 지연 import — 4주차 harness와 같은 이유).
  - 외부 DB: 실 파일을 임시 디렉터리로 복사하고 KANANA_EXTERNAL_DB_PATH 로 갈아끼운다.
    복사가 필요한 이유는 두 가지다.
      · seed(2026-07-07~17, 멤버 6명)가 기대값의 근거라서 빈 DB를 쓸 수 없다.
      · 일정 저장 요청이 들어오면 앱이 공유 저장소에 자동 동기화한다
        (fixed/external_mcp.py). 실 파일을 쓰면 Layer 1이 근거로 삼는 seed가 오염된다.
    외부 DB로 가는 모든 경로가 이 env 를 본다 —
    mcp_client.py:86, external_people_store.py:109, mcp_server/sqlite_mcp_server.py:25.
  - 새 대화: run_agent(question, conversation_id=None) 은 매번 새 conversation 을 만든다.

전제
  외부 seed 일정은 2026-07-07~17 이고 앱 기준 오늘은 2026-07-29 다. 즉 전부 과거다.
  "다음 주" 같은 질문이 0건인 건 정상이고, 그래서 케이스에 날짜를 명시했다.
  W5 는 그 전제 자체를 관찰하는 케이스다.

실행:
  uv run python tests/manual_week05_mcp_routing.py              # 케이스당 3회
  uv run python tests/manual_week05_mcp_routing.py --runs 1     # 스모크런
  uv run python tests/manual_week05_mcp_routing.py --case W2    # 한 케이스만
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

# python tests/... 직접 실행 시 프로젝트 루트가 sys.path에 없어 fixed/를 못 찾는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


SEED_RANGE = ("2026-07-07", "2026-07-17")

# 앱 DB 에 심어 둘 내 일정. 빈 DB 로는 W5(범위 밖 내 일정이 새는지)를 관측할 수 없다.
# 날짜를 과거로 둔 이유: "다음 주"로 물으면 요청 범위가 미래로 잡히므로
# 이 일정이 범위 밖이 되고, 그래도 rows 에 들어오면 누출이 눈에 보인다.
SEEDED_MY_SCHEDULE = {
    "kind": "personal_schedule",
    "title": "합성 내 일정",
    "date": "2026-07-19",
    "start_time": "15:00",
    "end_time": "16:00",
}

# 4주차까지의 내 저장소 tool. 5주차 질문에서 이게 불리면 저장소를 섞은 것이다.
MY_STORE_TOOLS = {
    "search_saved_requests",
    "search_personal_references",
    "personal_list_saved_schedules",
    "list_saved_requests",
    "get_saved_request",
}


# --- trace 읽기 -------------------------------------------------------------


class Run:
    """한 번의 agent 실행에서 판정에 필요한 것만 꺼내 둔다."""

    def __init__(self, answer: str, trace: dict[str, Any]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.results: list[tuple[str, Any]] = []
        for event in trace.get("events", []):
            if not isinstance(event, dict):
                continue
            name = event.get("tool_name")
            if not name:
                continue
            if event.get("event") == "tool_call":
                self.calls.append((name, event.get("arguments") or {}))
            elif event.get("event") == "tool_result":
                self.results.append((name, event.get("content")))

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args_of(self, tool_name: str) -> list[dict[str, Any]]:
        return [args for name, args in self.calls if name == tool_name]

    def rows_of(self, tool_name: str) -> list[dict[str, Any]]:
        """해당 tool 의 모든 호출 결과 rows 를 하나로 이어 붙인다."""

        rows: list[dict[str, Any]] = []
        for name, content in self.results:
            if name == tool_name and isinstance(content, dict):
                found = content.get("rows")
                if isinstance(found, list):
                    rows.extend(row for row in found if isinstance(row, dict))
        return rows

    def any_rows(self) -> bool:
        """어떤 tool 이든 근거 row 를 하나라도 받았는가."""

        return any(isinstance(content, dict) and content.get("rows") for _, content in self.results)

    def leaked_my_store(self) -> list[str]:
        return [name for name in self.names if name in MY_STORE_TOOLS]

    def tools_repr(self) -> str:
        return "|".join(self.names) if self.names else "(none)"


# --- 케이스별 판정 ----------------------------------------------------------
# 반환은 (통과, 메모). 통과가 None 이면 집계에서 빼고 메모만 남긴다 — 관찰용 케이스다.

Verdict = tuple[bool | None, str]


def judge_routing(run: Run) -> Verdict:
    """① 저장소 분리 + member_names 에 "나" 제외."""

    leaked = run.leaked_my_store()
    if "collect_member_schedules" not in run.names:
        reason = f"내 저장소 tool 호출: {leaked}" if leaked else "collect 미호출"
        return False, f"{reason} ({run.tools_repr()})"
    for args in run.args_of("collect_member_schedules"):
        members = args.get("member_names") or []
        if "나" in members:
            return False, f'member_names 에 "나" 포함: {members}'
    note = f"member_names={run.args_of('collect_member_schedules')[0].get('member_names')}"
    if leaked:
        note += f" · 내 저장소 tool 도 같이 호출됨: {leaked}"
    return True, note


def judge_search_query(run: Run) -> Verdict:
    """② 검색어를 짧은 명사로 골랐는가 — rows 가 비었는지로 판정한다."""

    if "search_previous_conversations" not in run.names:
        return False, f"검색 tool 미호출 ({run.tools_repr()})"
    queries = [args.get("query") for args in run.args_of("search_previous_conversations")]
    if not run.rows_of("search_previous_conversations"):
        return False, f"0건 — query={queries}"
    return True, f"query={queries}"


def judge_load_linkage(run: Run) -> Verdict:
    """③ conversation_id 를 검색 결과에서 가져왔는가 (지어내지 않았는가).

    처음엔 "load 를 불렀는가"로 판정했는데 그건 틀린 요구였다.
    search_previous_conversations 의 rows 에 이미 content 전문이 들어 있고
    seed 는 대화당 메시지가 1건이라, 검색 결과가 곧 대화 전문이다.
    agent 가 load 를 건너뛴 게 맞는 판단이었다 —
    프롬프트도 "대화 전문이 필요하면" 이라고 조건을 달았다.

    그래서 검증할 수 있는 건 하나뿐이다. load 를 부를 때 id 를 지어냈는지.
    안 불렀으면 판정하지 않는다(관찰).
    """

    if "search_previous_conversations" not in run.names:
        return False, f"외부 대화 검색을 하지 않았다 ({run.tools_repr()})"
    if "load_conversation_messages" not in run.names:
        return None, f"검색 결과로 답했다 — load 를 부를 필요가 없었다 ({run.tools_repr()})"
    known = {
        row.get("conversation_id")
        for row in run.rows_of("search_previous_conversations")
        if row.get("conversation_id")
    }
    used = [args.get("conversation_id") for args in run.args_of("load_conversation_messages")]
    invented = [value for value in used if value not in known]
    if invented:
        return False, f"검색에 없던 id 사용: {invented} (검색 결과: {sorted(known)})"
    return True, f"id={used}"


# 근거 없이 구체적인 시각을 말하면 지어낸 것으로 본다.
# 월("8월")은 질문을 되풀이한 것일 수 있어 시각만 본다.
TIME_PATTERN = re.compile(r"\d{1,2}시|\d{1,2}:\d{2}")


def judge_no_invention(run: Run) -> Verdict:
    """근거 row 가 0건일 때 없는 일정을 만들어내지 않는가.

    저장소 검사를 같이 하는 이유:
      처음엔 환각 여부만 봤는데, 내 저장소를 뒤져서 0건을 받은 실행이 통과로 잡혔다.
      남의 일정을 물었는데 내 DB 를 본 것 자체가 W3 과 같은 실패다.
      "0건이라 환각은 안 했다"로 넘어가면 routing 실패가 이 케이스에서 숨는다.
    """

    if not run.calls:
        return False, "tool 을 아예 호출하지 않았다"
    if leaked := run.leaked_my_store():
        return False, f"남의 일정을 내 저장소에서 찾았다: {leaked}"
    if run.any_rows():
        return None, "근거 row 가 있어 이 케이스의 판정 조건이 아니다"
    if found := TIME_PATTERN.findall(run.answer):
        return False, f"근거 0건인데 시각을 말했다: {found}"
    return True, "0건을 0건으로 답했다"


def observe_date_range(run: Run) -> Verdict:
    """내 일정이 조회 날짜 범위로 걸러지지 않는 현재 동작을 관찰한다.

    통과/실패로 세지 않는다. 날짜 필터를 넣을지 결정할 근거를 모으는 케이스다.

    빈 앱 DB 로는 관측이 안 된다 — 내 일정이 하나도 없으면 새어나올 것도 없다.
    그래서 build_runtime() 이 SEEDED_MY_SCHEDULE(2026-07-19)을 심어 둔다.
    """

    rows = run.rows_of("collect_member_schedules")
    mine = [row.get("date") for row in rows if row.get("member_name") == "나"]
    others = [row for row in rows if row.get("member_name") != "나"]
    requested = [(args.get("date_from"), args.get("date_to")) for args in run.args_of("collect_member_schedules")]
    leaked = [date for date in mine if not _within(date, requested)]
    verdict = f"요청범위={requested} · 외부={len(others)}건 · 나={mine or '없음'}"
    if leaked:
        verdict += f" · ⚠️ 범위 밖 내 일정이 섞였다: {leaked}"
    return None, verdict


def _within(date: str | None, ranges: list[tuple[Any, Any]]) -> bool:
    """요청 범위 중 하나에라도 들어가는 날짜인가. 범위를 못 읽으면 판단하지 않는다."""

    if not date or not ranges:
        return True
    for date_from, date_to in ranges:
        if not date_from or not date_to:
            return True
        if str(date_from) <= str(date) <= str(date_to):
            return True
    return False


def observe_unimplemented(run: Run) -> Verdict:
    """미구현 추가과제 tool 을 LLM 이 실제로 부르는지 관찰한다.

    부르면 None 을 받는다. Layer 1 의 마지막 테스트가 잡는 문제의 실제 영향이다.
    """

    if "create_shared_schedule" not in run.names:
        return None, f"create 미호출 ({run.tools_repr()})"
    contents = [content for name, content in run.results if name == "create_shared_schedule"]
    return False, f"미구현 tool 을 호출했다 → 결과: {contents}"


@dataclasses.dataclass
class Case:
    case_id: str
    group: str  # "prompt"(프롬프트 지시 검증) | "observe"(관찰만)
    question: str
    judge: Callable[[Run], Verdict]


CASES: list[Case] = [
    Case(
        "W1",
        "prompt",
        f"철수랑 영희 {SEED_RANGE[0]}부터 {SEED_RANGE[1]}까지 일정 좀 확인해줘",
        judge_routing,
    ),
    Case(
        "W2",
        "prompt",
        "철수가 예전에 API 관련해서 뭐라고 했는지 찾아줘",
        judge_search_query,
    ),
    Case(
        "W3",
        "prompt",
        "영희가 일정 공유할 때 뭐라고 했는지 원문 그대로 보여줘",
        judge_load_linkage,
    ),
    Case(
        "W4",
        "prompt",
        "철수 2026년 8월 일정 알려줘",
        judge_no_invention,
    ),
    Case(
        "W5",
        "observe",
        "다음 주에 철수랑 영희 시간 되는지 봐줘",
        observe_date_range,
    ),
    Case(
        "W6",
        "observe",
        "2026년 7월 30일 15시에 나랑 철수 회의를 공유 일정에 등록해줘",
        observe_unimplemented,
    ),
]


# --- 실행 ------------------------------------------------------------------


def build_runtime() -> Any:
    """임시 앱 DB + 외부 DB 복사본으로 갈아끼운 뒤 week5 runtime 을 만든다.

    CONFIG replace 가 import 보다 먼저여야 하므로 지연 import 한다.
    """

    import fixed.config as config_module

    tmp_dir = Path(tempfile.mkdtemp(prefix="week05_routing_"))

    # 외부 DB 는 seed 가 기대값의 근거라서 빈 파일을 쓸 수 없다 — 복사해서 쓴다.
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
        active_week=5,
    )
    config_module.CONFIG = test_config

    if not test_config.has_openai_key:
        print("❌ PROXY_TOKEN이 없습니다. .env에 키를 넣고 다시 실행하세요.", file=sys.stderr)
        sys.exit(1)

    # 내 일정을 하나 심는다. 이 저장은 공유 저장소에도 자동 동기화되지만
    # 위에서 외부 DB 를 복사본으로 갈아끼웠으므로 실 seed 는 안 건드린다.
    from fixed.app_store import AppSQLiteStore

    AppSQLiteStore(test_config.app_db_path).save_structured_request(dict(SEEDED_MY_SCHEDULE))

    print(f"# 격리: 앱 DB={test_config.app_db_path.name} · 외부 DB 복사본={external_copy}")
    print(f"# 심어둔 내 일정: {SEEDED_MY_SCHEDULE['date']} {SEEDED_MY_SCHEDULE['title']}")

    from fixed.agent_runtime import AgentRuntime

    return AgentRuntime(active_week=5)


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
    print(f"# Week 5 MCP routing — 케이스당 {options.runs}회, 새 대화")
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
            print(f"   {run_index} {mark}  {run.tools_repr()}")
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
