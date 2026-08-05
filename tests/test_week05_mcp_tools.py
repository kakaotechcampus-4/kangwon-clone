"""Week 5 MCP wrapper 테스트 — Layer 1 (LLM 없이 결정적으로 검증한다).

Week 3/4 테스트와 같은 원칙이다. 여기서 보는 것은 "wrapper가 계약대로 넘기고
받는가"이고, "LLM이 이 tool들을 제대로 고르는가"는 Layer 2에서 통과율로 잰다
(tests/manual_week04_query_reliability.py 와 같은 방식).
이 둘을 나눠야 agent 실험에서 실패했을 때 코드 탓인지 프롬프트 탓인지 구분된다.

5주차에서 계약이라고 부르는 것
  이 주차의 wrapper는 SQL을 쓰지 않는다. 그래서 검증할 게 "결과가 맞나"가 아니라
  "손대지 않고 넘겼나"다. 아래 테스트들은 대부분 그걸 본다 —
  정규화를 wrapper에서 또 하지 않았는지, 스펙에 없는 필드가 살아남았는지,
  None 과 [] 를 구분해서 넘겼는지.

격리 방법
  - 앱 DB: week05 모듈의 AppSQLiteStore를 고정 row를 돌려주는 stub으로 바꾼다.
    임시 DB 파일을 만드는 방법(week03 테스트 방식)보다 이게 나은 이유는,
    앱 DB에 내 일정이 몇 건 있는지에 결과가 안 흔들려서 rows 개수까지 단정할 수 있기 때문이다.
    실제 앱 DB에는 내가 쓰면서 쌓인 일정이 있고 그 수가 계속 바뀐다.
  - PERSONAL_SCHEDULES: 리스트 객체를 공유하므로 매 테스트마다 비운다.
  - 외부 DB(읽기 테스트): 갈아끼우지 않는다. 읽기만 하고 seed(2026-07-07~17, 멤버 6명)가
    고정이라 그 seed 자체가 기대값의 근거다.
  - 외부 DB(쓰기 테스트): 추가과제 create/delete 는 실제로 row 를 쓴다.
    temp_external_db fixture 로 tmp_path 의 새 파일에 격리한다. 실 DB 를 쓰면
    앞의 읽기 테스트들이 기대는 seed 를 오염시키고, 실패한 테스트가 쓰레기 row 를 남긴다.

일부러 여기 안 넣은 것
  - member_names 에 "나"를 넣었을 때 내 일정이 두 번 잡히는 현상:
    외부 저장소의 "나" row는 seed가 아니라 앱 자동 동기화로 생긴 것이라 개수가 변한다.
    애초에 "나를 넣지 않는다"는 프롬프트 지시라서, 지켜지는지는 Layer 2에서
    tool 호출 인자로 판정하는 게 맞다.
  - LLM 이 create/delete 를 부를 만한 상황에서 실제로 부르는가: Layer 2 의 몫이다.
    여기서는 "부르면 계약대로 동작하는가"만 본다.
    마지막 테스트는 구현 여부와 무관하게 "미구현인 채로 agent에 노출됐는지"를 계속 잡는다.

느린 이유
  MCP 호출마다 subprocess를 새로 띄우고 tool 목록을 다시 받는다(fixed/mcp_client.py).
  Week 3 테스트처럼 순식간에 끝나지 않는다. 정상이다.

실행:
  uv run pytest tests/test_week05_mcp_tools.py -q
"""

import inspect
import json
from typing import Any

import pytest

import student_parts.week05_load_kanas_past_conversations as week05
from fixed.session_scope import conversation_session_scope
from student_parts.week01_wake_up_nana import PERSONAL_SCHEDULES
from student_parts.week05_load_kanas_past_conversations import (
    _collect_member_schedules,
    _personal_schedules_for_current_scope,
    collect_member_schedules,
    create_shared_schedule,
    delete_shared_schedule,
    extract_schedules_from_history,
    list_shared_schedules,
    load_conversation_messages,
    search_previous_conversations,
)


# --- 외부 DB seed 상수 (fixed/external_people_store.py JULY_PRACTICE_*) -----
# 기대값을 매번 세지 않게 이름을 붙여둔다. seed가 바뀌면 여기만 고치면 된다.
SEED_DATE_FROM = "2026-07-07"
SEED_DATE_TO = "2026-07-17"
CHULSOO_SEED_COUNT = 3  # 철수: API 연동 실습 / 고객 인터뷰 / QA 리뷰
ROW_FIELDS = {"member_name", "title", "date", "start_time", "end_time", "notes"}


def payload_of(tool: Any, args: dict[str, Any]) -> dict[str, Any]:
    """@tool 은 JSON 문자열을 반환하므로 매번 파싱하는 걸 한 군데로 모은다."""

    return json.loads(tool.invoke(args))


@pytest.fixture(autouse=True)
def clean_personal_schedules():
    """PERSONAL_SCHEDULES 는 모듈 전역 리스트라 테스트끼리 샌다. 매번 비운다."""

    PERSONAL_SCHEDULES[:] = []
    yield
    PERSONAL_SCHEDULES[:] = []


@pytest.fixture
def fake_app_store(monkeypatch):
    """앱 DB 대신 고정 row를 돌려주는 store 를 끼운다.

    _personal_schedules_for_current_scope() 가 매 호출마다
    AppSQLiteStore(CONFIG.app_db_path) 를 새로 만들기 때문에 클래스만 갈아끼우면 된다.
    반환 리스트를 테스트가 직접 조작할 수 있게 rows 를 밖으로 넘긴다.
    """

    rows: list[dict[str, Any]] = []

    class FakeStore:
        def __init__(self, db_path):  # 경로는 받기만 하고 쓰지 않는다
            self.db_path = db_path

        def list_schedules(self, limit: int = 12, **kwargs):
            return list(rows[:limit])

    monkeypatch.setattr(week05, "AppSQLiteStore", FakeStore)
    return rows


@pytest.fixture
def temp_external_db(tmp_path, monkeypatch):
    """create/delete 테스트가 실 외부 DB 를 건드리지 않게 임시 파일로 돌린다.

    wrapper 는 db_path 를 인자로 받지 않는다(받게 만들면 tool 스키마에 테스트용
    인자가 새서 LLM 에게까지 노출된다). 그래서 모듈이 쓰는 call_mcp_tool_sync 를
    db_path 를 끼워 넣는 함수로 바꾼다.
    fixed/mcp_client.py 가 이 값을 MCP subprocess 의 KANANA_EXTERNAL_DB_PATH 로
    넘기고, mcp_server 가 그걸 읽어 자기 DB 로 쓴다.

    빈 파일에서 시작하므로 store 가 스키마를 만들고 실습용 seed 를 다시 심는다.
    seed 개수에 기대지 않도록 아래 테스트들은 전부 내가 만든 schedule_id 만 본다.
    """

    db_path = tmp_path / "external_write_test.sqlite3"
    real_call = week05.call_mcp_tool_sync

    def call_with_temp_db(tool_name: str, args: dict[str, Any]) -> str:
        return real_call(tool_name, args, db_path=db_path)

    monkeypatch.setattr(week05, "call_mcp_tool_sync", call_with_temp_db)
    return db_path


# --- 1. search_previous_conversations ---------------------------------------
# 이 tool의 검색은 LIKE '%query%' 부분 문자열 대조다(external_people_store.py).
# 4주차 벡터 검색과 규칙이 반대라서, 그 차이를 테스트로 못박아 둔다.


def test_짧은_키워드는_대화를_찾는다():
    payload = payload_of(search_previous_conversations, {"query": "회의"})

    assert payload["ok"] is True
    assert payload["rows"], "seed 대화에 '회의'가 있으므로 비면 안 된다"
    assert all(row.get("conversation_id") for row in payload["rows"])


def test_사용자_문장을_그대로_넣으면_못_찾는다():
    """LIKE 대조라 문장 전체가 DB에 통째로 있어야 하는데 그럴 리가 없다.

    이게 0건이라는 건 버그가 아니라 이 tool의 성질이다.
    그래서 프롬프트에서 '짧은 핵심 명사만 넣어라'를 지시해야 한다.
    """

    payload = payload_of(
        search_previous_conversations,
        {"query": "철수랑 영희랑 다음 주에 회의 언제 하기로 했었지?"},
    )

    assert payload["rows"] == []


def test_member_names가_빈_리스트면_대상이_없다는_뜻이다():
    """[] 는 '명시된 멤버가 없음'이라 0건이 맞다. or [] 로 뭉갰으면 여기서 걸린다."""

    payload = payload_of(search_previous_conversations, {"query": "회의", "member_names": []})

    assert payload["rows"] == []


def test_member_names가_None이면_전체_검색이다():
    """None 과 [] 가 같은 결과면 wrapper가 tri-state 를 흘린 것이다."""

    all_members = payload_of(search_previous_conversations, {"query": "회의", "member_names": None})
    no_member = payload_of(search_previous_conversations, {"query": "회의", "member_names": []})

    assert all_members["rows"], "None 은 전체 대상이라 결과가 있어야 한다"
    assert all_members["rows"] != no_member["rows"]


# --- 2. load_conversation_messages ------------------------------------------


def test_대화_메시지의_순서와_필드가_보존된다():
    """가공하지 않았다는 증거로 role 을 본다.

    가이드가 요구한 건 sender/content/created_at 뿐인데 role 도 같이 살아있다.
    필드를 골라 담았다면 사라졌을 값이라, pass-through 를 지켰다는 표시가 된다.
    """

    payload = payload_of(load_conversation_messages, {"conversation_id": "ext_yh"})

    assert payload["ok"] is True
    assert payload["rows"]
    for row in payload["rows"]:
        assert {"sender", "content", "created_at", "role"} <= set(row)

    created = [row["created_at"] for row in payload["rows"]]
    assert created == sorted(created), "시간순이 유지돼야 한다"


def test_없는_대화_id는_빈_rows로_돌아온다():
    """예외로 터지지 않아야 한다. LLM 이 id 를 잘못 넘길 수 있는 자리다."""

    payload = payload_of(load_conversation_messages, {"conversation_id": "ext_없는대화"})

    assert payload["ok"] is True
    assert payload["rows"] == []


def test_한글이_이스케이프되지_않는다():
    """json_payload() 가 ensure_ascii=False 를 쓰는지 문자열 단계에서 확인한다."""

    text = load_conversation_messages.invoke({"conversation_id": "ext_yh"})

    assert "\\u" not in text


# --- 3. extract_schedules_from_history --------------------------------------


def test_iso_datetime을_그대로_넘겨도_조회된다():
    """날짜 정리는 store/MCP 경계에서 한 번만 한다(가이드 84행).

    wrapper 가 T 를 자르지 않고 넘겨도 결과가 나오면, 중복 정규화가 필요 없다는 뜻이다.
    """

    payload = payload_of(
        extract_schedules_from_history,
        {"member_names": ["철수"], "date_from": f"{SEED_DATE_FROM}T09:00:00", "date_to": SEED_DATE_TO},
    )

    assert len(payload["rows"]) == CHULSOO_SEED_COUNT


def test_추출_결과가_요구된_필드를_유지한다():
    """가이드 85행. 스펙에 없는 source_conversation_id 까지 남는 게 pass-through 의 결과다."""

    payload = payload_of(
        extract_schedules_from_history,
        {"member_names": ["철수"], "date_from": SEED_DATE_FROM, "date_to": SEED_DATE_TO},
    )

    for row in payload["rows"]:
        assert ROW_FIELDS <= set(row)
    assert any(row.get("source_conversation_id") for row in payload["rows"])


def test_모르는_이름은_조회되지_않는다():
    """별칭 맵(EXTERNAL_MEMBER_ALIAS)이 비어 있어 이름은 정확히 일치해야 한다."""

    payload = payload_of(
        extract_schedules_from_history,
        {"member_names": ["Chulsoo"], "date_from": SEED_DATE_FROM, "date_to": SEED_DATE_TO},
    )

    assert payload["rows"] == []


def test_날짜_범위를_벗어나면_조회되지_않는다():
    """이 tool 은 날짜 폴백이 없다. '다음 주' 요청이 0건인 이유가 여기다."""

    payload = payload_of(
        extract_schedules_from_history,
        {"member_names": ["철수"], "date_from": "2026-08-01", "date_to": "2026-08-31"},
    )

    assert payload["rows"] == []


# --- 4. list_shared_schedules -----------------------------------------------


def test_필터_없이_부르면_기본_공유_일정과_요약이_온다():
    """개수는 단정하지 않는다 — 앱에서 일정을 저장하면 자동 동기화로 늘어난다."""

    payload = payload_of(list_shared_schedules, {})

    assert payload["ok"] is True
    assert payload["rows"]
    assert payload["schedule_summary"] != "조회된 외부 일정이 없습니다."


def test_멤버로_거르면_그_멤버_row만_온다():
    payload = payload_of(list_shared_schedules, {"member_names": ["철수"]})

    assert payload["rows"]
    assert {row["member_name"] for row in payload["rows"]} == {"철수"}


def test_공유_일정도_빈_리스트는_대상_없음이다():
    payload = payload_of(list_shared_schedules, {"member_names": []})

    assert payload["rows"] == []


# --- 5. _personal_schedules_for_current_scope -------------------------------
# 이 helper 의 존재 이유가 '남의 대화 일정을 내 busy time 으로 안 섞는 것'이라
# scope 필터와 중복 제거를 각각 본다.


def test_다른_대화의_임시_일정은_섞이지_않는다(fake_app_store):
    PERSONAL_SCHEDULES.extend(
        [
            {"id": "sch_here", "title": "내 대화 일정", "date": "2026-07-08", "session_id": "conv_a"},
            {"id": "sch_there", "title": "남의 대화 일정", "date": "2026-07-08", "session_id": "conv_b"},
        ]
    )

    with conversation_session_scope("conv_a"):
        rows = _personal_schedules_for_current_scope()

    assert [row["id"] for row in rows] == ["sch_here"]


def test_이미_저장된_일정은_임시_일정과_중복되지_않는다(fake_app_store):
    """1주차 임시 일정이 DB로 넘어갈 때 id 가 schedule_id 로 그대로 쓰인다
    (fixed/app_store.py: schedule_id = source_schedule_id or new_id("sch")).
    그래서 id 기준 비교가 실제로 걸린다.
    """

    fake_app_store.append(
        {"schedule_id": "sch_dup", "title": "저장된 회의", "date": "2026-07-08", "start_time": "10:00"}
    )
    PERSONAL_SCHEDULES.append(
        {"id": "sch_dup", "title": "저장된 회의", "date": "2026-07-08", "session_id": "conv_a"}
    )

    with conversation_session_scope("conv_a"):
        rows = _personal_schedules_for_current_scope()

    assert len(rows) == 1
    assert rows[0]["schedule_id"] == "sch_dup", "저장된 쪽이 기준이어야 한다"


# --- 6. collect_member_schedules -------------------------------------------
# helper 는 personal_schedules 를 인자로 받으므로 DB 없이 개수까지 단정할 수 있다.
# 이게 이 파일에서 가장 중요한 검증이다 — 6주차가 이 rows 를 busy_rows 로 쓴다.


def test_내_일정과_외부_일정이_같은_row_구조로_합쳐진다():
    """가이드 117행의 검증 기준 본체."""

    payload = _collect_member_schedules(
        member_names=["철수"],
        date_from=SEED_DATE_FROM,
        date_to=SEED_DATE_TO,
        personal_schedules=[
            {"id": "sch_mine", "title": "치과", "date": "2026-07-08", "start_time": "14:00", "end_time": "15:00"}
        ],
    )

    assert payload["ok"] is True
    assert payload["tool_name"] == "collect_member_schedules"
    assert len(payload["rows"]) == 1 + CHULSOO_SEED_COUNT
    assert {row["member_name"] for row in payload["rows"]} == {"나", "철수"}
    for row in payload["rows"]:
        assert ROW_FIELDS <= set(row)


def test_내_일정은_나로_라벨링된다():
    """앱 DB 의 owner 는 "me" 지만 외부 저장소의 내 복사본은 "나" 다
    (fixed/external_mcp.py PERSONAL_SHARED_MEMBER_NAME).
    여기서 owner 를 그대로 썼다면 같은 사람이 두 이름으로 갈렸을 것이다.
    """

    payload = _collect_member_schedules(
        member_names=[],
        date_from=SEED_DATE_FROM,
        date_to=SEED_DATE_TO,
        personal_schedules=[{"id": "sch_mine", "title": "치과", "date": "2026-07-08"}],
    )

    assert [row["member_name"] for row in payload["rows"]] == ["나"]


def test_시간이_비어_있으면_미정으로_채운다():
    """1주차 임시 일정은 start_time 이 None 일 수 있다. 실제 앱 DB 에도 그런 row 가 있다."""

    payload = _collect_member_schedules(
        member_names=[],
        date_from=SEED_DATE_FROM,
        date_to=SEED_DATE_TO,
        personal_schedules=[{"id": "sch_mine", "title": "테스트", "date": "2026-07-08", "start_time": None}],
    )

    row = payload["rows"][0]
    assert row["start_time"] == "미정"
    assert row["end_time"] == "미정"


def test_날짜_없는_내_일정은_제외된다():
    """날짜 없는 row 는 busy time 으로 쓸 수 없다."""

    payload = _collect_member_schedules(
        member_names=[],
        date_from=SEED_DATE_FROM,
        date_to=SEED_DATE_TO,
        personal_schedules=[
            {"id": "sch_no_date", "title": "날짜 미정 일정", "date": None},
            {"id": "sch_ok", "title": "치과", "date": "2026-07-08"},
        ],
    )

    assert [row["title"] for row in payload["rows"]] == ["치과"]


def test_schedule_summary가_rows를_반영한다():
    """LLM 이 근거로 읽는 문자열이라 rows 와 어긋나면 안 된다."""

    payload = _collect_member_schedules(
        member_names=["철수"],
        date_from=SEED_DATE_FROM,
        date_to=SEED_DATE_TO,
        personal_schedules=[{"id": "sch_mine", "title": "치과", "date": "2026-07-08", "start_time": "14:00"}],
    )

    assert payload["schedule_summary"].count("\n") == len(payload["rows"]) - 1
    assert "치과" in payload["schedule_summary"]
    assert "API 연동 실습" in payload["schedule_summary"]


def test_tool_경로도_같은_결과를_낸다(fake_app_store):
    """tool 은 _personal_schedules_for_current_scope() 를 스스로 부른다.

    store 를 stub 으로 끼웠으므로 helper 직접 호출과 결과가 같아야 한다.
    이게 갈리면 tool 이 인자를 helper 에 잘못 넘기고 있다는 뜻이다.
    """

    fake_app_store.append(
        {"schedule_id": "sch_mine", "title": "치과", "date": "2026-07-08", "start_time": "14:00", "end_time": "15:00"}
    )

    with conversation_session_scope("conv_a"):
        payload = payload_of(
            collect_member_schedules,
            {"member_names": ["철수"], "date_from": SEED_DATE_FROM, "date_to": SEED_DATE_TO},
        )

    assert len(payload["rows"]) == 1 + CHULSOO_SEED_COUNT
    assert {row["member_name"] for row in payload["rows"]} == {"나", "철수"}
    assert payload["schedule_summary"]


def test_내_일정도_조회_날짜_범위로_걸린다():
    """외부 멤버는 MCP 가 date_from/date_to 로 걸러주는데 내 일정만 안 걸리면
    한쪽만 필터된 rows 가 나간다.

    멘토 피드백(1차)에서 실제로 재현됐다 — 7월 범위 조회에 8월 개인 미팅이 섞였다.
    범위 밖이 빠지는 것과 범위 안이 남는 것을 같이 본다.
    필터가 과해서 내 일정을 통째로 날려도 여기서 잡힌다.
    """

    payload = _collect_member_schedules(
        member_names=[],
        date_from="2026-08-01",
        date_to="2026-08-31",
        personal_schedules=[
            {"id": "sch_old", "title": "지난주 회의", "date": "2026-07-19", "start_time": "15:00"},
            {"id": "sch_in", "title": "8월 미팅", "date": "2026-08-20", "start_time": "10:00"},
        ],
    )

    assert [row["title"] for row in payload["rows"]] == ["8월 미팅"]


def test_경계_날짜는_포함된다():
    """date_from/date_to 는 '이상·이하' 다. 경계를 빼면 '7일부터 17일까지' 요청에
    7일 일정이 사라지는데, 사용자는 그게 왜 없는지 알 방법이 없다.
    """

    payload = _collect_member_schedules(
        member_names=[],
        date_from=SEED_DATE_FROM,
        date_to=SEED_DATE_TO,
        personal_schedules=[
            {"id": "sch_start", "title": "시작일 일정", "date": SEED_DATE_FROM},
            {"id": "sch_end", "title": "종료일 일정", "date": SEED_DATE_TO},
        ],
    )

    assert [row["title"] for row in payload["rows"]] == ["시작일 일정", "종료일 일정"]


# --- 7. create/delete_shared_schedule (추가과제) -----------------------------
# 쓰기 tool 이라 temp_external_db 로 격리한다. 여기서 보는 계약은 두 가지다.
#   (1) 가이드 119~120행: create 한 row 가 list 에 나타나고 delete 로 사라진다
#   (2) 가이드 105행: schedule_id / source_conversation_id 가 보존된다
# 그리고 wrapper 가 값을 만지지 않는다는 규칙이 실제로 유지되는지도 같이 못박는다.

TEST_SID = "sch_test_create_0001"
TEST_DATE = "2026-09-09"  # 실습 seed(7월)와 겹치지 않는 날짜라 내 row 만 조회된다


def _create_test_schedule(**overrides: Any) -> dict[str, Any]:
    """테스트 row 하나를 등록한다. 바꿀 필드만 넘긴다."""

    args = {
        "member_name": "나",
        "title": "테스트 일정",
        "date": TEST_DATE,
        "start_time": "09:00",
        "end_time": "10:00",
        "schedule_id": TEST_SID,
    }
    args.update(overrides)
    return payload_of(create_shared_schedule, args)


def _rows_on_test_date() -> list[dict[str, Any]]:
    payload = payload_of(list_shared_schedules, {"date_from": TEST_DATE, "date_to": TEST_DATE})
    return payload.get("rows", [])


def test_등록한_공유_일정이_조회에_나타난다(temp_external_db):
    """가이드 119행의 검증 기준. create -> list 왕복이 이 tool 의 존재 이유다."""

    created = _create_test_schedule()

    assert created["ok"] is True
    assert created["tool_name"] == "create_shared_schedule"

    rows = _rows_on_test_date()
    assert [row["title"] for row in rows] == ["테스트 일정"]
    assert rows[0]["start_time"] == "09:00"


def test_schedule_id를_보존해야_나중에_지울_수_있다(temp_external_db):
    """가이드 105행 — 내가 넘긴 schedule_id 가 그대로 저장돼야 삭제/갱신 대상을 지정할 수 있다.

    wrapper 가 이 값을 만들거나 바꿨다면 등록한 뒤 다시 찾을 방법이 없어진다.
    """

    created = _create_test_schedule()

    assert created["shared_schedule"]["schedule_id"] == TEST_SID
    assert [row["schedule_id"] for row in _rows_on_test_date()] == [TEST_SID]


def test_source_conversation_id도_보존된다(temp_external_db):
    """앱 원본 request_id 로 나중에 지우는 경로(server docstring 90행)의 근거 필드다."""

    created = _create_test_schedule(schedule_id=None, source_conversation_id="req_from_app_0001")

    assert created["shared_schedule"]["source_conversation_id"] == "req_from_app_0001"


def test_같은_schedule_id로_다시_등록하면_중복이_아니라_갱신이다(temp_external_db):
    """schedule_id 를 None 으로도 그대로 넘겨야 이 UPSERT 가 작동한다.

    wrapper 가 "None 이면 빼고 보내자" 고 정리했다면 매번 새 id 가 생겨 중복 row 가 쌓인다.
    sync_status 로 저장소가 어느 쪽으로 처리했는지도 같이 확인한다.
    """

    first = _create_test_schedule()
    second = _create_test_schedule(title="갱신된 일정", start_time="11:00")

    assert first["shared_schedule"]["sync_status"] == "created"
    assert second["shared_schedule"]["sync_status"] == "updated"

    rows = _rows_on_test_date()
    assert len(rows) == 1, "같은 id 는 새 row 가 아니라 갱신이어야 한다"
    assert rows[0]["title"] == "갱신된 일정"
    assert rows[0]["start_time"] == "11:00"


def test_제목의_괄호는_저장소가_지운다(temp_external_db):
    """어디에도 안 적힌 동작이라 못박아 둔다.

    external_people_store.strip_parenthetical_text(256행)가 member_name/title/notes 의
    괄호와 그 안의 내용을 지운다. 즉 정규화는 저장소가 이미 다 하고 있다 —
    wrapper 에서 또 손댈 이유가 없다는 근거고, 동시에 제목에 괄호를 쓰면
    사라진다는 뜻이라 알고 있어야 한다.
    """

    _create_test_schedule(title="회의 (강남 지점)")

    assert [row["title"] for row in _rows_on_test_date()] == ["회의"]


def test_등록한_일정을_schedule_id로_삭제한다(temp_external_db):
    """가이드 120행의 검증 기준."""

    _create_test_schedule()

    deleted = payload_of(delete_shared_schedule, {"schedule_id": TEST_SID})

    assert deleted["ok"] is True
    assert deleted["deleted_count"] == 1
    assert deleted["deleted"][0]["schedule_id"] == TEST_SID
    assert _rows_on_test_date() == []


def test_대상을_지정하지_않은_삭제는_아무것도_지우지_않는다(temp_external_db):
    """wrapper 에 가드를 두지 않은 판단의 근거를 테스트로 고정한다.

    두 인자를 다 비우면 조건 없는 DELETE 가 될 수 있다. 지금은
    external_people_store.delete_shared_schedules(318행)가 그 경우 SQL 을 실행하지 않아서
    안전하다. wrapper 는 그 보장에 기대고 있으므로, 보장이 사라지면 여기가 먼저 빨간불이 된다.
    """

    _create_test_schedule()

    deleted = payload_of(delete_shared_schedule, {})

    assert deleted["deleted_count"] == 0
    assert [row["schedule_id"] for row in _rows_on_test_date()] == [TEST_SID], "내 row 가 살아있어야 한다"


# --- 8. week05_tools() ------------------------------------------------------


def test_미구현_tool이_agent에_노출되지_않는다():
    """추가과제를 구현하지 않으려면 week05_tools() 에서 빼라는 게 가이드 지시다(48행).

    미구현 tool 이 목록에 남아 있으면 LLM 이 그걸 부르고 None 을 받는다.
    구현하든 목록에서 빼든, 둘 중 하나를 하면 통과한다.

    판정을 소스의 TODO 마커로 하는 이유:
      본문이 `...` 뿐인 함수를 바이트코드로 구별할 수 없다. CPython 이 bare `...` 를
      죽은 코드로 지워서 co_consts 에 안 남는다(docstring 과 None 만 남는다).
      실제로 불러보는 방법도 못 쓴다 — 구현된 뒤에는 그 호출이 외부 DB 에 쓰기 때문이다.
    """

    def is_todo(tool: Any) -> bool:
        try:
            return "TODO" in inspect.getsource(tool.func)
        except (OSError, TypeError):  # 소스를 못 읽으면 판정하지 않는다
            return False

    unimplemented = sorted(tool.name for tool in week05.week05_tools() if is_todo(tool))

    assert not unimplemented, f"미구현 tool 이 agent 에 노출돼 있다: {unimplemented}"
