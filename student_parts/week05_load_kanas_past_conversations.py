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
    external_schedule_summary,
    normalize_external_member_names,
    normalize_external_schedule_date_bounds,
    strip_parenthetical_text,
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

    # TODO: SQLite 저장 일정과 현재 대화의 임시 일정을 합쳐 반환하세요.
    
    # 1. week3+ SQLite에 저장된 일정 (대화가 바뀌어도 남아 있는 영속 일정)
    #   kind 필터를 일부러 걸지 않음: schedules 테이블의 row는 개인이든 그룹이든 owner가 "나"인 내 일정이고,
    #   둘 다 그 시간에 내가 바쁘다는 근거임. kind="personal_schedule"로 좁히면 그룹 일정이 빠지는데,
    #   그룹 일정의 공유 저장소 복사본은 참석자 이름으로만 만들어져 외부 조회로도 안 잡힘(= 사각지대)
    #   list_schedules의 limit 기본값은 12이고, 일정 12개는 너무 적어서 바쁜 시간이 누락될 가능성 있음
    #   누락을 방지하기 위해 적절한 크기의 수가 필요함
    #   list_schedules 자체에는 상한 제약이 없지만, 이 프로젝트가 일정 조회 상한으로 쓰는 값(공유 일정 조회 스키마의 le=200)에 맞춰 200으로 정함
    saved_schedules = AppSQLiteStore(CONFIG.app_db_path).list_schedules(limit=200)

    # 2. week1 임시 일정(PERSONAL_SCHEDULES): 메모리 저장이므로 2번 필터링
    #   session_id != 현재 대화             -> 다른 대화의 임시 일정이므로 제외
    #   id가 SQLite schedule_id에 이미 있음  -> 같은 일정이 저장까지 끝난 것이므로 제외(중복 방지)
    saved_ids = {str(schedule.get("schedule_id")) for schedule in saved_schedules}
    current_scope = current_session_scope()
    pending_schedules = [
        schedule
        for schedule in PERSONAL_SCHEDULES
        # (session_id == 현재 대화: 현재 대화인가) and (id가 SQLite schedule_id에 없음: 영속 저장이 되어 있지 않은가)
        if _schedule_scope(schedule) == current_scope and str(schedule.get("id")) not in saved_ids
    ]

    # 3. 저장 일정 + 아직 저장 안된 현재 대화 임시 일정
    return [*saved_schedules, *pending_schedules]


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
    """앱 일정 row를 Week 2 StructuredRequest 기준으로 읽습니다.

    SQLite row는 'request_kind'로 개인/그룹을 구분합니다. Week 1 임시 일정 row에는 이 값이 없으므로 개인 일정으로 봅니다.
    """

    return StructuredRequest(
        kind="group_schedule" if row.get("request_kind") == "group_schedule" else "personal_schedule",
        title=row.get("title"),
        date=row.get("date"),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        members=row.get("attendees") or row.get("members") or [],
        original_text=str(row.get("title") or ""),
    )


def _my_schedule_notes(request: StructuredRequest) -> str:
    """내 일정 row가 개인 일정인지, 참석자가 있는 그룹인지 설명합니다."""

    if request.kind != "group_schedule":
        return "Nana 개인 일정"
    members = [str(member).strip() for member in (request.members or []) if str(member).strip()]
    return f"Nana 그룹 일정 · 참석자: {', '.join(members)}" if members else "Nana 그룹 일정"


def _dedupe_schedule_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 일정이 앱 DB와 공유 저장소 양쪽에서 들어와도 한 번만 남깁니다.

    앱 DB에 저장된 내 일정은 공유 저장소에도 자동 동기화되므로, member_names에 "나"가
    들어온 호출에서는 같은 일정이 두 경로로 들어옵니다. 앞에 오는 앱 DB row를 남깁니다.

    두 경로가 같은 일정을 서로 다르게 다듬기 때문에 값을 그대로 비교하면 안 됩니다.
      - 공유 저장소는 제목에서 소괄호를 지우고 공백을 하나로 줄입니다. 앱 DB는 원문을 둡니다.
      - 앱 DB 경로만 end_time "미정"을 "18:00"으로 바꿉니다. 그래서 end_time은 키에서 뺍니다.
        같은 사람이 같은 날 같은 시각에 시작하는 같은 제목의 일정은 하나로 봅니다.
      - start_time이 비어 있으면 공유 저장소는 "미정"으로 저장하므로 같은 값으로 맞춥니다.
    """

    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("member_name") or "").strip(),
            str(row.get("date") or "").strip(),
            str(row.get("start_time") or "").strip() or "미정",
            strip_parenthetical_text(str(row.get("title") or "")),
        )
        deduped.setdefault(key, row)
    return list(deduped.values())


def _collect_member_schedules(
    *,
    member_names: list[str],
    date_from: str,
    date_to: str,
    personal_schedules: list[dict[str, Any]],
) -> dict[str, Any]:
    """내 일정과 외부 멤버 일정을 같은 row 구조로 합칩니다."""

    # TODO: 내 SQLite/임시 일정과 외부 MCP 일정 rows를 같은 구조로 합치세요.

    # 출처가 다른 두 일정을 같은 row 구조로 통일하여 한 배열에 담기
    #   내 일정(personal_schedules) -> member_name에 "나"를 붙여 변환
    #   외부 멤버(MCP extract_...)  -> rows 그대로 사용
    # 공통 row 구조: member_name / title / date / start_time / end_time / notes
    # 왜? -> LLM이 "누가 언제 바쁜지"를 한 목록으로 읽기 위하여
    # 이름과 날짜 정규화 -> 내 일정 변환(+날짜 범위 필터) -> 외부 멤버 조회 -> 합치고 중복 제거 후 반환
    
    # 1. 외부 store 기준으로 멤버 이름과 날짜 범위를 정규화
    #   normalize_external_schedule_date_bounds: "2026-07-07T00:00" -> "2026-07-07" (날짜 부분만 추출)
    #   -> 아래 내 일정 날짜와 MCP 호출이 같은 기준을 사용하게 됨
    normalized_member_names = normalize_external_member_names(member_names)
    normalized_date_from, normalized_date_to = normalize_external_schedule_date_bounds(member_names, date_from, date_to)

    # 공통 row 구조 list
    rows: list[dict[str, Any]] = []

    # 2. 내 일정: personal_schedules는 날짜로 좁혀지지 않은 전체 목록이라 범위 규정
    #   _structured_request_from_schedule_row: SQLite row / week1 임시 row를 같은 모양으로 읽어주는 Adapter
    #   내 일정에는 member_name이 없으므로 "나"를 직접 붙여 외부 멤버 row와 구조를 맞춤
    for schedule in personal_schedules:
        request = _structured_request_from_schedule_row(schedule)
        schedule_date = str(request.date or "")
        if normalized_date_from and schedule_date < normalized_date_from:
            continue
        if normalized_date_to and schedule_date > normalized_date_to:
            continue
        rows.append(
            {
                "member_name": "나",
                "title": request.title or "제목 없음",
                "date": schedule_date,
                "start_time": request.start_time or "미정",
                "end_time": request.end_time or "미정",
                "notes": _my_schedule_notes(request),
            }
        )

    # 3. 외부 멤버 일정: MCP tool 결과(JSON 문자열)을 dict로 읽어 rows만 꺼냄
    #   "나"도 제외하지 않고 그대로 조회함
    #   앱이 내 일정을 공유 저장소에 member_name="나"로 자동 동기화하므로 2번의 앱 DB row와 겹치지만,
    #   공유 저장소에만 있는 "나" 일정(create_shared_schedule로 직접 등록한 것)은 앱 DB에 없어 여기서만 잡힘
    #   -> 겹치는 것은 4번의 _dedupe_schedule_rows가 걸러냄 (앞에 오는 앱 DB row가 남음)
    # 조회할 이름이 없으면 MCP 호출 생략

    if normalized_member_names:
        payload = json.loads(
            call_mcp_tool_sync(
                "extract_schedules_from_history",
                {
                    "member_names": normalized_member_names,
                    "date_from": normalized_date_from,
                    "date_to": normalized_date_to,
                },
            )
        )
        for row in payload.get("rows", []):
            rows.append(
                {
                    "member_name": row.get("member_name"),
                    "title": row.get("title"),
                    "date": row.get("date"),
                    "start_time": row.get("start_time"),
                    "end_time": row.get("end_time"),
                    "notes": row.get("notes"),
                }
            )

    # 4. 반환: 중복 제거한 rows + schedule_summary
    #   같은 일정이 앱 DB 경로와 공유 저장소 경로로 두 번 들어올 수 있어 여기서 한 번 걸러냄
    #   summary도 걸러낸 rows로 만들어야 rows 건수와 요약문 건수가 어긋나지 않음
    rows = _dedupe_schedule_rows(rows)
    return {
        "member_names": normalized_member_names,
        "date_from": normalized_date_from,
        "date_to": normalized_date_to,
        "rows": rows,
        "schedule_summary": external_schedule_summary(rows),
    }



@tool(args_schema=SearchPreviousConversationsInput)
def search_previous_conversations(
    query: str,
    member_names: list[str] | None = None,
    limit: int = 5,
) -> str:
    """
    외부 SQLite에 저장된 '다른 사람(외부 멤버)'의 지난 대화를 검색합니다.
    팀원·동료가 예전에 남긴 얘기, '누가 뭐라고 했는지'를 찾을 때 씁니다.
    나와 나눈 대화를 찾는 search_conversation_messages와는 다른 저장소입니다.

    query는 저장된 메시지 원문에 그대로 들어 있는 연속된 낱말이어야 합니다.
    서버가 부분 문자열로만 대조하므로 조사·서술어가 붙거나 낱말 순서가 다르면 0건이 됩니다.
      "온보딩 세션" (O)  /  "하린 온보딩" (X, 원문은 "하린: ... 온보딩 세션 ...")
      "데이터 정리" (O)  /  "데이터 정리를 언제" (X)
    사람 이름은 query에 넣지 말고 member_names로 넘깁니다.
    0건이 나오면 query를 더 짧은 명사 하나로 줄여 한 번 더 검색합니다.
    그래도 0건이면 query를 비우고 member_names만으로 그 사람의 대화를 가져올 수 있습니다.
    """

    # TODO: call_mcp_tool_sync("search_previous_conversations", args)를 호출하고 결과 문자열을 반환하세요.
    
    # 외부 대화 검색은 MCP 서버(mcp_server/sqlite_mcp_server.py)가 담당
    # member_names는 []와 None의 의미가 달라 인자 변환 없이 그대로 전달
    #   None -> 전체 멤버 검색
    #   [] -> 멤버를 지정했으나 유효한 이름이 없음
    return call_mcp_tool_sync(
        "search_previous_conversations",
        {
            "query": query,
            "member_names": member_names,
            "limit": limit,
        }
    )

@tool(args_schema=LoadConversationMessagesInput)
def load_conversation_messages(conversation_id: str) -> str:
    """
    외부 대화 하나의 전체 메시지를 시간순으로 불러옵니다.
    conversation_id는 search_previous_conversations 결과 rows에서 얻습니다.
    (사용자에게 conversation_id를 되묻지 말고 먼저 검색으로 찾습니다)
    """

    # TODO: call_external_tool_payload("load_conversation_messages", {"conversation_id": ...}) 결과를 JSON으로 반환하세요.
    
    # MCP 결과 문자열을 dict로 파싱하여 반환
    # call_external_tool_payload의 결과로 dict를 받으므로
    # json_payload로 다시 JSON 문자열로 변환하여 tool 반환 규격을 맞춤
    payload = call_external_tool_payload(
        "load_conversation_messages",
        {
            "conversation_id": conversation_id
        },
    )

    # Message의 sender/content/created_at과 시간 순서를 보존해야 하므로 가공 없이 payload 넘김
    return json_payload(payload)


@tool(args_schema=ExtractSchedulesFromHistoryInput)
def extract_schedules_from_history(member_names: list[str], date_from: str, date_to: str) -> str:
    """외부 SQLite 이전 대화에서 '외부 멤버'의 일정만 추출합니다.

    내 일정은 포함되지 않으므로, 요청에 "나"가 함께 있으면 collect_member_schedules를 씁니다.
    """

    # TODO: call_mcp_tool_sync("extract_schedules_from_history", args)를 호출해 외부 멤버 busy-time rows를 반환하세요.
    
    # 이름 정규화와 날짜(ISO datetime -> 날짜) 정리는 외부 store 경계에서 이미 처리하므로, 중복 변환하지 않고 인자를 그대로 넘김
    # MCP 결과로 rows(member_name/title/date/start_time/end_time/notes), schedule_summary가 들어있고,
    # 이미 JSON 문자열이므로 가공 없이 그대로 반환
    return call_mcp_tool_sync(
        "extract_schedules_from_history",
        {
            "member_names": member_names,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@tool(args_schema=CreateSharedScheduleInput)
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
    """
    외부 공유 일정 저장소에 일정을 등록하거나 갱신합니다.
    다른 사람 이름으로 '공유 일정'을 만들어 달라는 요청에 사용합니다.
    내 개인 일정을 앱 DB에 저장하는 save_structured_request와는 다른 저장소입니다.
    """

    # TODO: call_mcp_tool_sync("create_shared_schedule", args)로 공유 일정 row를 생성/갱신하세요.
    
    # 인자 8개를 변환 없이 그대로 전달 (이름/날짜/빈 값 정규화는 store가 한 번만 처리)
    #   schedule_id 없음 -> 새 row 생성 (sync_status: "created")
    #   schedule_id 있음 -> 같은 id row를 갱신 (sync_status: "updated")
    #   schedule_id / source_conversation_id -> 나중에 삭제 또는 갱신 시 row를 찾을 때 필요하므로 보존
    # MCP 결과 = {ok, tool_name, shared_schedule} JSON 문자열 -> 가공 없이 그대로 반환
    return call_mcp_tool_sync(
        "create_shared_schedule",
        {
            "member_name": member_name,
            "title": title,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "notes": notes,
            "source_conversation_id": source_conversation_id,
            "schedule_id": schedule_id,
        },
    )


@tool(args_schema=DeleteSharedScheduleInput)
def delete_shared_schedule(
    schedule_id: str | None = None,
    source_conversation_id: str | None = None,
) -> str:
    """
    외부 공유 일정 저장소에서 일정을 삭제합니다.
    '공유 일정'을 지워 달라는 요청에 사용하며,
    앱 개인 일정을 지우는 personal_delete_saved_schedules와는 다른 저장소입니다.
    """

    # TODO: call_mcp_tool_sync("delete_shared_schedule", args)로 공유 일정을 삭제하세요.
    
    # create_shared_schedule에서 보존해 둔 두 값(schedule_id, source_conversation_id)이 삭제 대상을 찾는 기준이 됨
    #   두 인자는 AND가 아닌 OR 조건으로, 둘 중 하나만 넘겨도 해당 row를 삭제
    #   둘 다 없으면 store가 아무것도 지우지 않음 (전체 삭제 방지 장치) -> wrapper에서 별도 방어 불필요
    # MCP 결과 = {ok, tool_name, deleted_count, deleted} JSON 문자열 -> 가공 없이 그대로 반환
    return call_mcp_tool_sync(
        "delete_shared_schedule",
        {
            "schedule_id": schedule_id,
            "source_conversation_id": source_conversation_id,
        },
    )



@tool(args_schema=ListSharedSchedulesInput)
def list_shared_schedules(
    member_names: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source_conversation_id: str | None = None,
    limit: int = 50,
) -> str:
    """
    외부 공유 일정 저장소에 등록된 일정을 조회합니다. 필터가 없으면 기본 공유 일정을 반환합니다.
    앱에 저장된 내 일정 목록(personal_list_saved_schedules)과는 다른 저장소입니다.
    '공유 일정'이 등록돼 있는지 확인할 때 사용합니다.
    """

    # TODO: call_mcp_tool_sync("list_shared_schedules", args)로 공유 일정 저장소 rows를 조회하세요.
    
    # 필터 4종(member_names/date_from/date_to/source_conversation_id)을 변환 없이 그대로 전달
    #   4종 모두 없음         -> "필터 없음"으로 간주하여 기본 공유 일정 반환
    #   member_names=None   -> 멤버 필터 없음 (기본 일정 반환 조건 포함)
    #   member_names=[]     -> 멤버 지정했으나 유효한 이름이 없음 -> 빈 결과
    #   => None을 []로 바꾸면 기본 일정 대신 0건이 되므로 별도 변환하지 않음
    # MCP 결과 = {ok, tool_name, rows, schedule_summary} JSON 문자열 -> 가공 없이 그대로 반환
    return call_mcp_tool_sync(
        "list_shared_schedules",
        {
            "member_names": member_names,
            "date_from": date_from,
            "date_to": date_to,
            "source_conversation_id": source_conversation_id,
            "limit": limit,
        },
    )


@tool(args_schema=CollectMemberSchedulesInput)
def collect_member_schedules(member_names: list[str], date_from: str, date_to: str) -> str:
    """내 일정과 다른 사람들의 일정을 하나의 목록으로 모읍니다.

    여러 사람이 언제 바쁜지 확인할 때(회의·약속 시간 조율) 이 도구 하나로 처리하며,
    사람마다 따로 조회하지 않습니다.
    member_names에 "나"를 포함하면 내 일정까지 같은 목록에 합쳐집니다.
    date_from·date_to 범위는 외부 멤버뿐 아니라 내 일정에도 그대로 적용됩니다.
    """

    # TODO: 내 일정과 외부 멤버 busy-time rows를 모아 JSON 문자열로 반환하세요.
    
    # helper 2개 사용
    #   _personal_schedules_for_current_scope() -> "나"의 일정(SQLite 저장분 + 현재 대화 임시분)
    #   _collect_member_schedules(...) -> 위 내 일정 + 외부 멤버 일정을 같은 row 구조로 병합
    # -> 내 일정 조회 출처는 tool이 결정, 병합 규칙은 helper가 담당
    payload = _collect_member_schedules(
        member_names=member_names,
        date_from=date_from,
        date_to=date_to,
        personal_schedules=_personal_schedules_for_current_scope(),
    )

    # helper 결과에 이미 member_names/date_from/date_to/rows/schedule_summary가 들어 있으므로
    # key를 별도로 만들지 않고 그대로 JSON 문자열로 변환해 반환
    return json_payload(payload)


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


def week05_prompt_parts() -> list[str]:
    """1~5주차 system prompt 조각을 누적합니다."""

    return [
        *week04_prompt_parts(),
        # TODO: Week 5 Kana history agent system prompt를 자유롭게 추가하세요.

        # 출처 3분법 + 신호별 도구 매핑
        #   도구 사용법과 인자 규칙은 각 tool docstring에 두고,
        #   여기서는 "무엇이 보이면 어느 쪽인가"만 정한다.
        (
            "요청에 사람 이름이 나오면 그 사람의 지난 대화는 search_previous_conversations, "
            "일정은 collect_member_schedules로 조회한다. "
            "'공유 일정'은 list/create/delete_shared_schedule을 쓴다. "
            "'나와 나눈', '내가 저장한'처럼 내 것이 분명할 때만 Week 1~4 도구를 쓴다. "
            "어느 저장소인지는 각 도구 설명에 적혀 있으니 그에 따른다."
        ),

        # 대화 요청에서 "누구의 대화인가"를 가르는 규칙
        #   조건을 하나로 묶었더니 거꾸로 발동했다(6차 관측).
        #     "나랑 나눈"이 명시된 F3·HF3에서 외부까지 불러 forbid를 위반했고,
        #     정작 아무 이름도 없는 HA4·NQ7·NQ8·NS2·NS4에서는 내 대화만 보고 끝냈다.
        #   -> 세 경우를 각각 따로 적는다. 특히 이름이 없을 때의 기본값이
        #      내 대화 쪽으로 쏠려 있으므로 외부 조회를 명시적으로 요구한다.
        (
            "대화를 찾아 달라는 요청은 누구의 대화인지로 갈린다. "
            "① '나', '내가', '나랑'이 들어가면 내 대화만 본다. 외부 멤버 대화는 조회하지 않는다. "
            "② 다른 사람 이름이 나오면 그 사람의 외부 대화만 본다. 내 대화는 조회하지 않는다. "
            "③ 이름도 '나'도 없는 '지난 대화', '예전 얘기', '~라는 말이 나온 대화' 요청은 "
            "내 대화만 보고 끝내지 않는다. search_previous_conversations로 외부 멤버 대화를 "
            "반드시 함께 확인한 뒤 답한다."
        ),

        # 행동 원칙 — 전 도구 공통
        (
            "되묻지 말고 먼저 조회한다. "
            "어떤 도구로 처리할지 판단했으면 그 판단을 설명하지 말고 그 도구를 호출한다. "
            "지시대명사('그거', '아까 그것')가 가리키는 대상은 검색으로 확정하고, "
            "질문 문구를 그대로 제목으로 쓰지 않는다."
        ),

        # 답변 근거 — 전 도구 공통
        (
            "rows와 schedule_summary를 근거로 답한다. "
            "0건이면 도구 설명에 적힌 대로 한 번 더 시도하고, 그러고도 비었을 때만 없다고 답한다. "
            "추측으로 빈 시간을 단정하지 않는다."
        ),
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
