from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from fixed.app_store import AppSQLiteStore
from fixed.config import CONFIG
from fixed.external_mcp import call_external_tool_payload
from fixed.external_people_store import (
    PERSONAL_SHARED_MEMBER_NAME,
    external_schedule_summary,
    normalize_external_member_names,
    normalize_external_schedule_date_bounds,
)
from fixed.llm import chat_model
from fixed.mcp_client import (
    call_local_mcp_tool,
    call_local_mcp_tool_sync,
    load_local_mcp_tools,
    load_local_mcp_tools_sync,
)
from fixed.runtime_clock import current_app_date_iso
from fixed.session_scope import DEFAULT_SESSION_SCOPE, current_session_scope
from student_parts.week01_wake_up_nana import PERSONAL_SCHEDULES, join_system_prompt
from student_parts.week02_structure_natural_language_requests import StructuredRequest
from student_parts.week04_retrieve_nanas_memory import week04_prompt_parts, week04_tools


_WEEK05_AGENT: Any | None = None


# [5주차 수강생 구현 가이드]
#
# 목표
#   외부 SQLite/MCP 서버에 있는 Kana의 이전 대화와 공유 일정을 LangChain agent가 사용할 수 있게 감쌉니다.
#   학생이 직접 SQL을 작성하는 주차가 아니라, MCP tool을 호출하고 그 결과를 agent용 JSON으로 전달하는
#   wrapper tool을 만드는 주차입니다.
#
# 과제 구성
#   - 메인과제: 외부 SQLite/MCP 서버의 이전 대화를 검색·로드하고 그 대화에서 일정을 추출하는
#     MCP wrapper 세로 슬라이스에 더해, 공유 일정 조회(list_shared_schedules)와
#     내 일정·외부 멤버 busy-time을 한 rows로 합치는 collect_member_schedules까지 완성합니다.
#     이 두 tool은 Week 6 Kana 하위 agent가 그대로 재사용하는 연결 지점이라 메인과제입니다.
#   - 추가 과제: 공유 일정 저장소에 row를 직접 등록·삭제하는 create_shared_schedule/delete_shared_schedule
#     wrapper를 확장합니다. 구현하지 않으려면 week05_tools() 목록에서 이 두 tool을 빼면 됩니다.
#
# 구현 위치와 사용할 코드
#   - 이 파일(student_parts/week05_load_kanas_past_conversations.py)의 @tool wrapper 함수들을 구현합니다.
#   - 실제 외부 SQLite/MCP tool 구현은 mcp_server/sqlite_mcp_server.py에 있으며, 학생은 이 파일을 직접 수정하지 않습니다.
#   - MCP 호출은 fixed/mcp_client.py의 call_local_mcp_tool_sync를 이 파일에서 별칭으로 둔
#     call_mcp_tool_sync(tool_name, args)를 사용합니다.
#   - load_conversation_messages는 fixed/external_mcp.py의 call_external_tool_payload(...)를 사용해
#     외부 tool payload를 dict로 받은 뒤 json_payload()로 감쌉니다.
#   - 멤버 이름/날짜 정규화와 요약은 fixed/external_people_store.py의
#     normalize_external_member_names(), normalize_external_schedule_date_bounds(),
#     external_schedule_summary()를 사용합니다.
#   - 내 일정 수집은 _personal_schedules_for_current_scope()에서 처리합니다. 이 helper는
#     fixed/app_store.py의 AppSQLiteStore(CONFIG.app_db_path).list_schedules(...)와
#     student_parts/week01_wake_up_nana.py의 PERSONAL_SCHEDULES 중 현재 대화 범위 row를 합칩니다.
#   - Week 3+ AppSQLiteStore는 개인/그룹 일정을 저장할 때 공유 일정 저장소에 자동 동기화할 수 있습니다.
#     list_shared_schedules wrapper(메인)는 공유 저장소 row를 직접 확인할 때,
#     create/delete_shared_schedule wrapper(추가)는 row를 직접 등록/삭제해 보정할 때 사용합니다.
#   - week05_tools()는 student_parts/week04_retrieve_nanas_memory.py의 week04_tools() 위에
#     Week 5 MCP wrapper tool들을 누적해 Week 5 단일 agent에 공개합니다.
#     추가 과제(create/delete_shared_schedule)를 구현하지 않으려면 week05_tools() 목록에서 해당 tool을 빼면 됩니다.
#
# 메인과제 구현 대상
#   1. search_previous_conversations
#      - query, member_names, limit를 받습니다.
#      - 이 파일의 call_mcp_tool_sync("search_previous_conversations", args)를 호출하고 결과 문자열을 그대로 반환합니다.
#      - 멤버 이름 정규화는 외부 SQLite store/MCP 경계에서 한 번만 처리하므로 wrapper에서 중복 변환하지 않습니다.
#
#   2. load_conversation_messages
#      - conversation_id로 외부 SQLite/MCP helper에서 이전 대화 메시지를 조회합니다.
#      - call_external_tool_payload("load_conversation_messages", {"conversation_id": conversation_id})를 사용합니다.
#      - 대화 메시지의 sender/content/created_at 순서가 보존되도록 결과를 가공하지 않습니다.
#
#   3. extract_schedules_from_history
#      - member_names, date_from, date_to를 받습니다.
#      - call_mcp_tool_sync("extract_schedules_from_history", args)를 호출합니다.
#      - 날짜 형식 정리는 외부 SQLite store/MCP 경계에서 한 번만 처리합니다.
#      - 결과 rows는 member_name/title/date/start_time/end_time/notes 필드를 유지해야 합니다.
#
#   4. list_shared_schedules
#      - call_mcp_tool_sync("list_shared_schedules", args)를 호출해 공유 일정 저장소 row를 조회합니다.
#      - 공유 저장소 자체를 확인할 때는 "나"를 포함한 등록 row를 조회합니다.
#      - 필터 없이 호출하면 외부 실습용 기본 공유 일정 row가 우선 반환될 수 있습니다.
#      - Week 6 Kana 하위 agent가 공유 저장소 row 조회에 그대로 사용하는 tool입니다.
#
#   5. collect_member_schedules
#      - 3주차 이후 저장된 내 일정은 앱 SQLite에서 읽고, 현재 대화의 임시 일정만 추가로 합칩니다.
#      - 외부 멤버 일정은 call_mcp_tool_sync("extract_schedules_from_history", args) 결과를 이 tool 안에서 읽습니다.
#      - 두 출처를 member_name/title/date/start_time/end_time/notes가 있는 rows 배열로 직접 합칩니다.
#      - schedule_summary도 함께 반환해 LLM이 바쁜 시간을 자연어로 설명할 수 있게 합니다.
#      - PERSONAL_SCHEDULES는 현재 대화 범위의 아직 DB에 없는 임시 일정만 합치고, SQLite에 이미 저장된 일정과 중복하지 않습니다.
#      - Week 6 추가 과제(find_common_available_slots)가 이 tool의 rows를 busy_rows 근거로 사용합니다.
#
# 추가 과제 구현 대상 (구현하지 않으려면 week05_tools() 목록에서 해당 tool을 제거)
#   1. create_shared_schedule / delete_shared_schedule
#      - 각각 call_mcp_tool_sync("create_shared_schedule" / "delete_shared_schedule", args)를 호출합니다.
#      - 공유 일정 저장소 row를 생성/삭제할 때 MCP tool 결과를 그대로 전달합니다.
#      - schedule_id 또는 source_conversation_id를 보존해야 나중에 수정/삭제 동기화가 가능합니다.
#
# 책임 경계
#   mcp_server/sqlite_mcp_server.py의 @mcp.tool 구현은 학생 구현 대상이 아닙니다.
#   이 파일의 wrapper tool은 직접 SQL이나 중복 정규화 helper를 두지 않고 store/MCP helper의 결과 JSON을 전달합니다.
#   week05_tools()는 Week 1-4 도구에 외부 SQLite/MCP 일정 도구를 누적합니다.
#   외부 멤버 busy-time 조회와 공유 저장소 row 조회는 Week 5 범위지만, 여러 사람의 최종 회의 시간 선택은 Week 6 범위입니다.
#
# 검증 방법
#   - 메인과제: ./run.sh --week5에서 외부 팀원 일정 조회 요청을 입력하고, trace에서
#     search_previous_conversations, load_conversation_messages, extract_schedules_from_history 중
#     어떤 tool이 어떤 순서로 호출됐는지 확인합니다.
#     collect_member_schedules 결과 rows에 "나"와 외부 멤버 일정이 같은 구조로 들어 있고,
#     list_shared_schedules 결과에 rows와 schedule_summary가 유지되는지 확인합니다.
#   - 추가 과제: create_shared_schedule로 등록한 row가 list_shared_schedules 조회에 나타나고
#     delete_shared_schedule로 삭제되는지 확인합니다.
#
# 함수별 동작 설명 ([메인]/[추가]/[공통]은 각 함수가 속한 과제 티어입니다)
#   - [메인] _schedule_scope(schedule)
#     Week 1 임시 일정이 어느 대화 범위에 속하는지 읽습니다. session_id가 없으면 기본 scope로 처리합니다.
#
#   - [메인] _personal_schedules_for_current_scope()
#     Week 3 이후 SQLite에 저장된 내 일정과 현재 대화에만 남아 있는 Week 1 임시 일정을 합칩니다.
#     이미 SQLite에 저장된 일정과 임시 일정이 중복되지 않도록 schedule_id/id를 기준으로 한 번 걸러냅니다.
#
#   - [공통] json_payload(payload)
#     외부 MCP 결과나 내부 helper 결과 dict를 한글이 보존되는 JSON 문자열로 바꿉니다.
#
#   - [메인] SearchPreviousConversationsInput / LoadConversationMessagesInput / ExtractSchedulesFromHistoryInput
#     외부 이전 대화 검색, 대화 메시지 로드, 외부 대화에서 일정 추출 tool의 입력 스키마입니다.
#
#   - [메인] ListSharedSchedulesInput / CollectMemberSchedulesInput
#     공유 일정 저장소 row 조회와, 내 일정·외부 멤버 busy-time을 같은 rows 배열로 합치는 tool의 입력 스키마입니다.
#
#   - [추가] CreateSharedScheduleInput / DeleteSharedScheduleInput
#     외부 공유 일정 저장소에 row를 생성, 삭제할 때 쓰는 입력 스키마입니다.
#
#   - [메인] _structured_request_from_schedule_row(row)
#     SQLite schedule row나 Week 1 임시 schedule row를 Week 2 StructuredRequest 모양으로 읽습니다.
#     뒤에서 내 일정 row를 외부 멤버 row와 같은 구조로 맞출 때 사용합니다.
#
#   - [메인] _collect_member_schedules(...)
#     내 일정과 외부 멤버 일정을 같은 member_name/title/date/start_time/end_time/notes row 구조로 합칩니다.
#     외부 멤버 이름과 날짜 범위는 fixed/external_people_store.py helper로 정규화합니다.
#
#   - [메인] search_previous_conversations(...)
#     외부 SQLite/MCP 서버에 저장된 과거 대화를 검색합니다. wrapper는 query/member_names/limit를 넘기고 결과 문자열을 그대로 반환합니다.
#
#   - [메인] load_conversation_messages(conversation_id)
#     검색으로 찾은 특정 외부 대화의 전체 메시지를 불러옵니다. sender/content/created_at 순서를 보존합니다.
#
#   - [메인] extract_schedules_from_history(...)
#     외부 멤버의 이전 대화에서 일정 또는 바쁜 시간 row를 추출합니다.
#
#   - [메인] list_shared_schedules(...)
#     공유 일정 저장소 row를 조회하는 MCP wrapper입니다. Week 6 Kana 하위 agent도 그대로 사용합니다.
#
#   - [메인] collect_member_schedules(...)
#     내 일정과 외부 멤버 busy-time을 한 번에 모으는 Week 5 핵심 tool입니다.
#     Week 6의 공통 가능 시간 결정 tool(추가 과제)이 이 rows를 busy_rows 근거로 사용합니다.
#
#   - [추가] create_shared_schedule(...) / delete_shared_schedule(...)
#     공유 일정 저장소에 row를 등록/삭제하는 MCP wrapper입니다. source_conversation_id와 schedule_id를 보존해 동기화 근거로 씁니다.
#
#   - [공통] week05_tools()
#     Week 4까지의 tool에 외부 대화/MCP/공유 일정 tool을 누적합니다.
#
#   - [공통] week05_system_prompt() / week05_prompt_parts()
#     개인 저장/RAG는 이전 주차 도구로, 외부 멤버 대화와 일정은 MCP wrapper로 처리하도록 agent 역할을 설명합니다.
#
#   - [공통] build_week05_agent() / build_week_agent()
#     Week 1~5 tool을 가진 agent를 한 번만 만들고 재사용합니다.


call_mcp_tool = call_local_mcp_tool
call_mcp_tool_sync = call_local_mcp_tool_sync
load_langchain_mcp_tools = load_local_mcp_tools
load_langchain_mcp_tools_sync = load_local_mcp_tools_sync


def _schedule_scope(schedule: dict[str, Any]) -> str:
    return str(schedule.get("session_id") or DEFAULT_SESSION_SCOPE)


def _personal_schedules_for_current_scope() -> list[dict[str, Any]]:
    """SQLite 저장 일정과 현재 대화의 임시 일정만 group 조율 후보로 사용합니다."""

    personal_schedule = [schedule for schedule in PERSONAL_SCHEDULES if _schedule_scope(schedule) == current_session_scope()]
    update_personal_schedule = []
    saved_schedule = AppSQLiteStore(CONFIG.app_db_path)
    saved_schedule_list = saved_schedule.list_schedules(limit=1000)
    saved_schedule_ids = {row.get("schedule_id") for row in saved_schedule_list}
    for x in personal_schedule:
        if x.get("id") not in saved_schedule_ids:
            update_personal_schedule.append(x)
    return update_personal_schedule + saved_schedule_list


def json_payload(payload: dict[str, Any]) -> str:
    """도구 반환용 dict를 한글이 깨지지 않는 JSON 문자열로 변환합니다."""

    return json.dumps(payload, ensure_ascii=False)


class SearchPreviousConversationsInput(BaseModel):
    """외부 이전 대화 검색 입력입니다."""

    query: str
    member_names: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=50)


class LoadConversationMessagesInput(BaseModel):
    """외부 대화 메시지 조회 입력입니다."""

    conversation_id: str


class ExtractSchedulesFromHistoryInput(BaseModel):
    """외부 멤버 일정 추출 입력입니다."""

    member_names: list[str]
    date_from: str
    date_to: str


class CreateSharedScheduleInput(BaseModel):
    """공유 일정 생성 입력입니다."""

    member_name: str
    title: str
    date: str
    start_time: str
    end_time: str = "미정"
    notes: str | None = None
    source_conversation_id: str | None = None
    schedule_id: str | None = None


class DeleteSharedScheduleInput(BaseModel):
    """공유 일정 삭제 입력입니다."""

    schedule_id: str | None = None
    source_conversation_id: str | None = None


class ListSharedSchedulesInput(BaseModel):
    """공유 일정 조회 입력입니다."""

    member_names: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    source_conversation_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CollectMemberSchedulesInput(BaseModel):
    """내 일정과 외부 멤버 busy-time 수집 입력입니다."""

    member_names: list[str]
    date_from: str
    date_to: str


def _structured_request_from_schedule_row(row: dict[str, Any]) -> StructuredRequest:
    """앱 일정 row를 Week 2 StructuredRequest 기준으로 읽습니다."""

    return StructuredRequest(
        kind="personal_schedule",
        title=row.get("title"),
        date=row.get("date"),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        members=row.get("attendees") or row.get("members") or [],
        original_text=str(row.get("title") or ""),
    )


def _collect_member_schedules(
    *,
    member_names: list[str],
    date_from: str,
    date_to: str,
    personal_schedules: list[dict[str, Any]],
) -> dict[str, Any]:
    """내 일정과 외부 멤버 일정을 같은 row 구조로 합칩니다."""

    normalized_member_names = normalize_external_member_names(member_names)
    normalized_date_from, normalized_date_to = normalize_external_schedule_date_bounds(
        member_names, date_from, date_to
    )

    personal_rows = []
    for schedule in personal_schedules:
        structured = _structured_request_from_schedule_row(schedule)
        if structured.date and not (normalized_date_from <= structured.date <= normalized_date_to):
            continue
        personal_rows.append(
            {
                "member_name": PERSONAL_SHARED_MEMBER_NAME,
                "title": structured.title,
                "date": structured.date,
                "start_time": structured.start_time,
                "end_time": structured.end_time,
                "notes": None,
            }
        )

    external_payload = json.loads(
        call_mcp_tool_sync(
            "extract_schedules_from_history",
            {
                "member_names": normalized_member_names,
                "date_from": normalized_date_from,
                "date_to": normalized_date_to,
            },
        )
    )
    external_rows = external_payload.get("rows", [])

    rows = personal_rows + external_rows
    return {"rows": rows, "schedule_summary": external_schedule_summary(rows)}


@tool(
    args_schema=SearchPreviousConversationsInput,
    description="[search_previous_conversations 규칙] 다른 멤버와 나눈 과거 대화를 외부 SQLite/MCP에서 검색한다. '나'의 기록은 다루지 않으니 Week 1-4 도구를 써라.",
)
def search_previous_conversations(
    query: str,
    member_names: list[str] | None = None,
    limit: int = 5,
) -> str:
    """[search_previous_conversations 규칙]
    다른 멤버와 나눈 과거 대화를 외부 SQLite/MCP 저장소에서 검색한다.
    '나'의 개인 메모나 저장 일정을 찾을 때는 이 tool이 아니라 Week 1-4 개인 검색 도구를 써라.
    query에는 조사/불용어를 제거하지 않은 핵심 명사나 구 하나만 넣어라 — 서버가 그대로 매칭한다.
    member_names를 생략(None)하면 전체 멤버를 대상으로 검색하지만, 빈 리스트를 넘기면 빈 결과만 온다 —
    특정 멤버로 좁히고 싶을 때만 채워라. 결과는 매칭된 메시지 스니펫과 conversation_id다. 대화 전체를
    읽어야 하면 load_conversation_messages를 이어서 호출해라.
    """

    previous_conversation = call_mcp_tool_sync("search_previous_conversations", {"query":query, "member_names" : member_names, "limit" : limit})
    return previous_conversation


@tool(
    args_schema=LoadConversationMessagesInput,
    description="[load_conversation_messages 규칙] search_previous_conversations로 찾은 conversation_id 하나의 메시지 전체를 시간순으로 불러온다.",
)
def load_conversation_messages(conversation_id: str) -> str:
    """[load_conversation_messages 규칙]
    search_previous_conversations로 찾은 conversation_id 하나의 메시지 전체를 불러온다.
    sender/content/created_at을 시간순 그대로 반환한다. 검색 스니펫만으로는 맥락이 부족해서
    특정 대화의 전체 내용을 근거로 정확히 답해야 할 때 사용해라. 순서를 바꾸거나 요약해서
    다른 사실처럼 전달하지 마라.
    """

    all_previous_conversation_messages = call_external_tool_payload("load_conversation_messages", {"conversation_id": conversation_id})
    return json_payload(all_previous_conversation_messages)


@tool(
    args_schema=ExtractSchedulesFromHistoryInput,
    description="[extract_schedules_from_history 규칙] 다른 멤버의 과거 기록에서 일정/바쁜 시간을 date_from~date_to 범위로 추출한다. '나'의 일정은 다루지 않는다.",
)
def extract_schedules_from_history(member_names: list[str], date_from: str, date_to: str) -> str:
    """[extract_schedules_from_history 규칙]
    다른 멤버의 과거 기록에서 일정/바쁜 시간 row를 date_from~date_to 범위로 추출한다.
    '나'의 일정을 조회할 때는 이 tool이 아니라 앱 내부 저장 일정 도구나 collect_member_schedules를
    써라. date_from/date_to는 절대 날짜(YYYY-MM-DD)로 넘겨라. 멤버 이름/날짜 형식 정규화는
    서버가 처리하므로 임의로 형식을 바꾸지 마라.
    """

    previous_individual_schedules = call_mcp_tool_sync("extract_schedules_from_history", {"member_names": member_names, "date_from": date_from, "date_to": date_to})
    return previous_individual_schedules


@tool(
    args_schema=CreateSharedScheduleInput,
    description="[create_shared_schedule 규칙] 외부 공유 일정 저장소에 일정을 등록하거나(schedule_id가 있으면) 갱신한다.",
)
def create_shared_schedule(
    member_name: str,
    title: str,
    date: str,
    start_time: str,
    end_time: str = "미정",
    notes: str | None = None,
    source_conversation_id: str | None = None,
    schedule_id: str | None = None,
) -> str:
    """[create_shared_schedule 규칙]
    외부 공유 일정 저장소에 일정 row를 등록하거나, 같은 schedule_id를 넘기면 그 row를 갱신한다.
    여러 멤버가 함께 보는 공유 일정을 직접 만들거나 고칠 때만 써라. schedule_id나
    source_conversation_id는 이전 조회/등록 결과에서 그대로 재사용해라 — 값을 새로 지어내면
    별개의 row가 생겨 동기화가 끊긴다.
    """

    shared_schedule = call_mcp_tool_sync("create_shared_schedule", {
        "member_name": member_name,
        "title": title,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "notes": notes,
        "source_conversation_id": source_conversation_id,
        "schedule_id": schedule_id,
    })
    return shared_schedule


@tool(
    args_schema=DeleteSharedScheduleInput,
    description="[delete_shared_schedule 규칙] schedule_id 또는 source_conversation_id로 공유 일정 저장소의 일정을 삭제한다.",
)
def delete_shared_schedule(
    schedule_id: str | None = None,
    source_conversation_id: str | None = None,
) -> str:
    """[delete_shared_schedule 규칙]
    schedule_id 또는 source_conversation_id로 식별되는 공유 일정 row를 삭제한다.
    삭제 대상 ID는 반드시 list_shared_schedules나 create_shared_schedule 결과에서 얻은 실제 값을
    써라. 둘 다 비우면 아무것도 삭제되지 않는다.
    """

    delete_schedule = call_mcp_tool_sync("delete_shared_schedule", {
        "schedule_id": schedule_id,
        "source_conversation_id": source_conversation_id,
    })
    return delete_schedule


@tool(
    args_schema=ListSharedSchedulesInput,
    description="[list_shared_schedules 규칙] 나와 다른 멤버가 함께 보는 공유 일정 저장소를 멤버/기간으로 필터링해 조회한다.",
)
def list_shared_schedules(
    member_names: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source_conversation_id: str | None = None,
    limit: int = 50,
) -> str:
    """[list_shared_schedules 규칙]
    나와 다른 멤버가 함께 보는 공유 일정 저장소의 row를 조회한다.
    member_names/date_from/date_to/source_conversation_id로 필터링할 수 있다. 특정 멤버나
    기간을 물었다면 반드시 그 필터를 채워라 — 필터 없이 호출하면 실습용 기본 공유 일정이
    우선 반환되어 원하는 답이 아닐 수 있다.
    """

    shared_schedules = call_mcp_tool_sync("list_shared_schedules", {"member_names": member_names, "date_from": date_from, "date_to": date_to, "source_conversation_id": source_conversation_id, "limit": limit})
    return shared_schedules


@tool(
    args_schema=CollectMemberSchedulesInput,
    description="[collect_member_schedules 규칙] '나'의 일정과 다른 멤버들의 바쁜 시간을 한 번에 모은다. 여러 사람 일정을 같이 봐야 할 때 우선 써라.",
)
def collect_member_schedules(member_names: list[str], date_from: str, date_to: str) -> str:
    """[collect_member_schedules 규칙]
    '나'의 일정(앱에 저장된 것 + 이번 대화의 임시 일정)과 다른 멤버들의 바쁜 시간을
    member_name/title/date/start_time/end_time/notes 구조의 같은 rows로 합쳐 반환한다.
    여러 사람의 일정을 함께 확인하거나 회의 가능한 시간을 물어보는 질문에는 개별 도구 대신
    이 tool을 우선 써라.
    """

    personal_schedules = _personal_schedules_for_current_scope()
    personal_schedule_dict = _collect_member_schedules(member_names = member_names, date_from = date_from, date_to = date_to, personal_schedules = personal_schedules)
    return json_payload(personal_schedule_dict)


def week05_tools() -> list[Any]:
    """4주차까지의 도구에 외부 SQLite/MCP 일정 도구를 누적한 목록입니다."""

    return [
        *week04_tools(),
        search_previous_conversations,
        load_conversation_messages,
        extract_schedules_from_history,
        create_shared_schedule,
        delete_shared_schedule,
        list_shared_schedules,
        collect_member_schedules,
    ]


def week05_system_prompt() -> str:
    """5주차 단일 agent가 따르는 시스템 프롬프트입니다."""

    return join_system_prompt(week05_prompt_parts())


WEEK05_MEMORY_PROMPT = f"""[Week 5 외부 대화/공유 일정 규칙]
Week 5부터 너는 앱 내부에만 있던 "나"의 기록과 별도로, 외부 SQLite/MCP 서버에 있는 다른 멤버들의 이전 대화와 공유 일정 저장소를 다룬다.
오늘 날짜는 {current_app_date_iso()}이다. 아래 tool들의 date_from/date_to나 date 인자에 '오늘/내일/이번 주/다음 주' 같은 상대 표현이 나오면 반드시 이 날짜를 기준으로 절대 날짜(YYYY-MM-DD)로 바꿔서 넘겨라.
1. search_previous_conversations: 다른 멤버와 나눈 과거 대화를 검색한다. query에는 조사나 불용어를 제거하지 않은 핵심 명사/구 하나만 넣어라 — 서버가 그대로 매칭한다. member_names를 생략(None)하면 전체 멤버를 대상으로 검색하지만, 빈 리스트를 넘기면 "지정된 멤버 없음"으로 처리되어 항상 빈 결과가 되므로 특정 멤버를 검색할 때만 채워라.
2. load_conversation_messages: search_previous_conversations로 찾은 conversation_id의 메시지를 sender/content/created_at 순서 그대로 불러온다. 여기서 읽은 내용만 근거로 답하고, 순서를 바꾸거나 요약해서 다른 사실처럼 말하지 마라.
3. extract_schedules_from_history: 외부 멤버의 과거 기록에서 일정/바쁜 시간 row를 date_from~date_to 범위로 추출한다. 날짜 형식과 멤버 이름은 서버가 정규화하므로 네가 임의로 형식을 바꾸거나 보정하지 마라.
4. list_shared_schedules: 나와 외부 멤버가 함께 보는 공유 일정 저장소의 row를 조회한다. 필터 없이 호출하면 실습용 기본 공유 일정이 우선 반환될 수 있으니, 특정 멤버·기간을 물었다면 반드시 그 필터를 채워서 호출하라.
5. collect_member_schedules: "나"의 일정(Week 3 이후 SQLite 저장분과 이번 대화의 임시 일정)과 외부 멤버들의 바쁜 시간을 member_name/title/date/start_time/end_time/notes 구조의 같은 rows로 합쳐 반환한다. 여러 사람의 일정을 함께 확인하거나 회의 가능 시간을 물어보는 질문에는 이 tool을 우선 사용하라.
6. create_shared_schedule / delete_shared_schedule: 공유 일정 저장소에 row를 직접 등록하거나 삭제한다. 등록/조회로 받은 schedule_id 또는 source_conversation_id를 그대로 기억해두었다가 같은 일정을 다시 수정·취소할 때 넘겨서 같은 row를 가리키게 하라. 값을 새로 지어내면 별개의 row가 생겨 동기화가 끊긴다.
위 tool들이 돌려주는 rows나 schedule_summary가 비어 있으면 관련 대화나 공유 일정이 없다고 사실대로 답하고 지어내지 마라. Week 1~4의 개인 저장/RAG 도구는 "나"의 기록만 다루고 Week 5 도구는 다른 멤버와 공유 저장소를 다루므로, 질문이 누구의 일정/대화에 관한 것인지부터 구분한 뒤 알맞은 tool을 골라라."""


def week05_prompt_parts() -> list[str]:
    """1~5주차 system prompt 조각을 누적합니다."""

    return [
        *week04_prompt_parts(),
        WEEK05_MEMORY_PROMPT,
    ]


def build_week05_agent() -> object:
    """Week 1-5 누적 tool 목록을 노출하는 단일 LangChain agent를 만듭니다."""

    if not CONFIG.has_openai_key:
        raise RuntimeError("PROXY_TOKEN이 .env에 필요합니다.")
    global _WEEK05_AGENT
    if _WEEK05_AGENT is None:
        _WEEK05_AGENT = create_agent(
            model=chat_model(),
            tools=week05_tools(),
            system_prompt=week05_system_prompt(),
        )
    return _WEEK05_AGENT


def build_week_agent() -> object:
    """active-week registry가 호출하는 표준 Week agent builder입니다."""

    return build_week05_agent()
