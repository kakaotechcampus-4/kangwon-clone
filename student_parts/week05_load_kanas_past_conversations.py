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

call_mcp_tool = call_local_mcp_tool
call_mcp_tool_sync = call_local_mcp_tool_sync
load_langchain_mcp_tools = load_local_mcp_tools
load_langchain_mcp_tools_sync = load_local_mcp_tools_sync


_SELF_MEMBER_NAMES = {"나", "본인", "나 자신"}
_SCHEDULE_ID_KEYS = ("schedule_id", "id", "source_schedule_id")


def _schedule_scope(schedule: dict[str, Any]) -> str:
    return str(schedule.get("session_id") or DEFAULT_SESSION_SCOPE)


def _schedule_ids(schedule: dict[str, Any]) -> set[str]:
    """일정 row가 가질 수 있는 원본/저장 식별자를 모읍니다."""

    return {
        str(schedule.get(key) or "").strip()
        for key in _SCHEDULE_ID_KEYS
        if str(schedule.get(key) or "").strip()
    }


def _personal_schedules_for_current_scope() -> list[dict[str, Any]]:
    """SQLite 저장 일정과 현재 대화의 임시 일정을 중복 없이 합칩니다."""

    sqlite_rows = AppSQLiteStore(CONFIG.app_db_path).list_schedules(limit=200)

    merged_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for row in sqlite_rows:
        identities = _schedule_ids(row)
        if identities and identities & seen_ids:
            continue

        merged_rows.append(dict(row))
        seen_ids.update(identities)

    active_scope = current_session_scope()
    for schedule in PERSONAL_SCHEDULES:
        if _schedule_scope(schedule) != active_scope:
            continue

        identities = _schedule_ids(schedule)
        if identities and identities & seen_ids:
            continue

        merged_rows.append(dict(schedule))
        seen_ids.update(identities)

    return merged_rows


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
    external_member_names = [
        name
        for name in normalized_member_names
        if str(name).strip() not in _SELF_MEMBER_NAMES
    ]

    normalized_date_from, normalized_date_to = (
    normalize_external_schedule_date_bounds(
        external_member_names,
        date_from,
        date_to,
    )
)

    personal_requests = (
        (schedule_row, _structured_request_from_schedule_row(schedule_row))
        for schedule_row in personal_schedules
    )

    rows: list[dict[str, Any]] = [
        {
            "member_name": "나",
            "title": request.title or "제목 없음",
            "date": request.date,
            "start_time": request.start_time or "미정",
            "end_time": request.end_time or "미정",
            "notes": schedule_row.get("notes"),
        }
        for schedule_row, request in personal_requests
        if request.date is not None
        and normalized_date_from <= request.date <= normalized_date_to
    ]

    if external_member_names:
        external_result = call_mcp_tool_sync(
            "extract_schedules_from_history",
            {
                "member_names": external_member_names,
                "date_from": normalized_date_from,
                "date_to": normalized_date_to,
            },
        )

        if isinstance(external_result, str):
            try:
                external_payload: dict[str, Any] = json.loads(external_result)
            except json.JSONDecodeError:
                external_payload = {}
        elif isinstance(external_result, dict):
            external_payload = external_result
        else:
            external_payload = {}

        external_rows = external_payload.get("rows", [])
        if isinstance(external_rows, list):
            rows.extend(
                {
                    "member_name": row.get("member_name"),
                    "title": row.get("title"),
                    "date": row.get("date"),
                    "start_time": row.get("start_time"),
                    "end_time": row.get("end_time"),
                    "notes": row.get("notes"),
                }
                for row in external_rows
                if isinstance(row, dict)
                and str(row.get("member_name") or "").strip()
                not in _SELF_MEMBER_NAMES
            )

    rows.sort(
        key=lambda row: (
            str(row.get("date") or ""),
            str(row.get("start_time") or ""),
            str(row.get("member_name") or ""),
        )
    )

    return {
        "rows": rows,
        "schedule_summary": external_schedule_summary(rows),
    }


@tool(args_schema=SearchPreviousConversationsInput)
def search_previous_conversations(
    query: str,
    member_names: list[str] | None = None,
    limit: int = 5,
) -> str:
    """외부 SQLite 데이터베이스에 저장된 이전 대화를 검색합니다."""

    return call_mcp_tool_sync(
        "search_previous_conversations",
        {
            "query": query,
            "member_names": member_names,
            "limit": limit,
        },
    )


@tool(args_schema=LoadConversationMessagesInput)
def load_conversation_messages(conversation_id: str) -> str:
    """외부 SQLite 데이터베이스에서 특정 이전 대화의 모든 메시지를 불러옵니다."""

    payload = call_external_tool_payload(
        "load_conversation_messages",
        {"conversation_id": conversation_id},
    )
    return json_payload(payload)


@tool(args_schema=ExtractSchedulesFromHistoryInput)
def extract_schedules_from_history(
    member_names: list[str],
    date_from: str,
    date_to: str,
) -> str:
    """외부 SQLite 이전 대화에서 멤버별 일정을 추출합니다."""

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
    """외부 MCP 공유 일정 저장소에 일정을 등록하거나 갱신합니다."""

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
    """외부 MCP 공유 일정 저장소에서 일정을 삭제합니다."""

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
    """외부 MCP 공유 일정 저장소에 등록된 일정을 조회합니다."""

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
def collect_member_schedules(
    member_names: list[str],
    date_from: str,
    date_to: str,
) -> str:
    """내 일정과 다른 사람들의 일정을 MCP SQLite 기록에서 모읍니다."""

    result = _collect_member_schedules(
        member_names=member_names,
        date_from=date_from,
        date_to=date_to,
        personal_schedules=_personal_schedules_for_current_scope(),
    )
    return json_payload(result)


def week05_tools() -> list[Any]:
    """4주차까지의 도구에 외부 SQLite/MCP 일정 도구를 누적합니다."""

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
        (
            "너는 Kanana의 Week 5 Kana history agent다. "
            f"현재 날짜는 앱 시작 시 OS에서 읽은 {current_app_date_iso()}이다."
        ),
        (
            "외부 SQLite/MCP 서버에 이미 구현된 기능을 wrapper tool로 사용하고, "
            "필요한 도구만 선택한다. 서버 내부 동작을 추측하거나 로컬에서 다시 구현하지 않는다."
        ),
        (
            "사용자가 외부 멤버와 예전에 나눈 대화를 찾으면 "
            "search_previous_conversations를 먼저 사용한다. "
            "특정 conversation_id의 전체 메시지가 필요하면 load_conversation_messages를 사용한다."
        ),
        (
            "외부 멤버의 이전 대화에서 일정이나 바쁜 시간을 찾을 때는 "
            "extract_schedules_from_history를 사용한다. "
            "내 일정과 외부 멤버 일정을 비교할 때는 collect_member_schedules를 사용한다."
        ),
        (
            "공유 일정 저장소를 확인할 때는 list_shared_schedules를 사용한다. "
            "사용자가 등록이나 삭제를 명확하게 요청했을 때만 "
            "create_shared_schedule 또는 delete_shared_schedule을 사용한다."
        ),
        (
            "내 개인 일정과 앱 내부 대화는 Week 1~4 도구로 처리하고, "
            "외부 멤버의 대화와 일정만 Week 5 MCP 도구로 처리한다. "
            "도구가 반환한 식별자와 데이터는 임의로 바꾸거나 만들지 않는다."
        ),
        (
            "최종 답변은 도구가 반환한 실제 rows, messages, schedule_summary만 근거로 작성한다. "
            "여러 사람의 최종 공통 가능 시간 계산은 Week 6 범위이므로 "
            "이번 주에는 바쁜 시간 조회와 정리까지만 수행한다."
        ),
    ]


def build_week05_agent() -> object:
    """Week 1~5 누적 tool 목록을 노출하는 단일 LangChain agent를 만듭니다."""

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
