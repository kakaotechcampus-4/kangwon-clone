from __future__ import annotations

import json
from pathlib import Path
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


class PersonalScheduleGateway:
    """'나'의 일정 데이터에 접근하는 방법을 캡슐화합니다.

    지금은 AppSQLiteStore(SQLite)를 쓰지만, 나중에 DB 엔진이 바뀌거나
    접근 방식이 달라져도 이 클래스 내부만 고치면 되고, 이 클래스를
    사용하는 tool 함수들은 전혀 영향받지 않습니다.
    """

    # limit은 store의 필수 인자라 값을 안 줄 수 없다. 이 숫자에 실질적 의미를
    # 부여할 근거(실사용 데이터, 서비스 정책 등)가 이 프로젝트에는 없으므로,
    # 정확한 근거를 대는 대신 이 한계 자체를 정직하게 남겨둔다: 이 값은
    # "충분히 크다고 가정한 값"일 뿐이며, 실제 서비스라면 사용자당 일정
    # 개수의 실측 데이터를 바탕으로 재산정해야 한다.
    _MAX_SCHEDULES_IN_RANGE = 500  # 근거 없는 추정치, 실사용 데이터 필요 (알려진 한계)

    def __init__(self, db_path: str | Path) -> None:
        self._store = AppSQLiteStore(db_path)

    def list_within_range(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        """지정한 기간 안의 내 일정만 DB 쿼리 단계에서 걸러서 가져옵니다."""

        return self._store.list_schedules(
            date_from=date_from, date_to=date_to, limit=self._MAX_SCHEDULES_IN_RANGE
        )


def _personal_schedule_gateway() -> PersonalScheduleGateway:
    return PersonalScheduleGateway(CONFIG.app_db_path)


class ExternalScheduleGateway:
    """MCP를 통한 외부 멤버 데이터 접근 방법을 캡슐화합니다.

    지금은 로컬 MCP subprocess(call_mcp_tool_sync)를 쓰지만, 나중에 MCP
    서버가 여러 개로 늘어나거나 통신 방식이 바뀌어도 이 클래스만 고치면
    됩니다.
    """

    def search_conversations(self, query: str, member_names: list[str] | None, limit: int) -> str:
        args = {"query": query, "member_names": member_names, "limit": limit}
        return call_mcp_tool_sync("search_previous_conversations", args)

    def load_messages(self, conversation_id: str) -> dict[str, Any]:
        return call_external_tool_payload(
            "load_conversation_messages", {"conversation_id": conversation_id}
        )

    def extract_schedules(self, member_names: list[str], date_from: str, date_to: str) -> str:
        args = {"member_names": member_names, "date_from": date_from, "date_to": date_to}
        return call_mcp_tool_sync("extract_schedules_from_history", args)

    def list_shared_schedules(self, **kwargs: Any) -> str:
        return call_mcp_tool_sync("list_shared_schedules", kwargs)

    def create_shared_schedule(self, **kwargs: Any) -> str:
        return call_mcp_tool_sync("create_shared_schedule", kwargs)

    def delete_shared_schedule(self, **kwargs: Any) -> str:
        return call_mcp_tool_sync("delete_shared_schedule", kwargs)


_external_gateway = ExternalScheduleGateway()


def _schedule_scope(schedule: dict[str, Any]) -> str:
    return str(schedule.get("session_id") or DEFAULT_SESSION_SCOPE)


def _personal_schedules_for_current_scope(date_from: str, date_to: str) -> list[dict[str, Any]]:
    """SQLite 저장 일정과 현재 대화의 임시 일정만 group 조율 후보로 사용합니다."""

    gateway = _personal_schedule_gateway()
    saved_schedules = gateway.list_within_range(date_from, date_to)

    saved_ids = {
        row.get("schedule_id")
        for row in saved_schedules
        if row.get("schedule_id")
    }

    current_scope = current_session_scope()
    temp_schedules = [
        schedule
        for schedule in PERSONAL_SCHEDULES
        if _schedule_scope(schedule) == current_scope
        and (schedule.get("schedule_id") or schedule.get("id")) not in saved_ids
    ]

    return [*saved_schedules, *temp_schedules]


def json_payload(payload: dict[str, Any]) -> str:
    """도구 반환용 dict를 한글이 깨지지 않는 JSON 문자열로 변환합니다."""

    return json.dumps(payload, ensure_ascii=False)


class MCPToolError(Exception):
    """MCP tool 호출이 실패했거나 응답 형식이 예상과 다를 때 발생시킵니다."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def _distinct_conversation_ids(rows: list[dict[str, Any]]) -> list[str]:
    """rows에서 중복 없는 conversation_id 목록을 순서 보존하며 뽑습니다."""

    seen: list[str] = []
    for row in rows:
        conversation_id = row.get("conversation_id")
        if conversation_id and conversation_id not in seen:
            seen.append(conversation_id)
    return seen


def _parse_mcp_rows(result: str) -> list[dict[str, Any]]:
    """MCP tool의 JSON 문자열 결과에서 rows를 꺼냅니다.

    ok=false 이거나 응답 형식이 예상과 다르면 MCPToolError를 던집니다.
    예외 메시지 자체에는 원본 응답(result)을 담지 않습니다 — 민감할 수 있는
    원본 데이터가 호출부의 반환값에 그대로 노출되는 것을 막기 위함입니다.
    실제로 rows가 비어 있는 경우(ok=true, rows=[])만 빈 리스트를 정상 반환합니다.
    """

    try:
        parsed = json.loads(result)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MCPToolError("MCP 응답 JSON 파싱 실패", code="parse_error") from exc

    if not isinstance(parsed, dict):
        raise MCPToolError("예상치 못한 MCP 응답 형식", code="invalid_shape")

    if parsed.get("ok") is False:
        raise MCPToolError("MCP tool이 실패를 명시적으로 반환함", code="mcp_reported_failure")

    rows = parsed.get("rows")
    if not isinstance(rows, list):
        raise MCPToolError("MCP 응답에 유효한 rows가 없음", code="invalid_rows")

    return [row for row in rows if isinstance(row, dict)]


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

    현재 이 파일의 다른 함수에서는 사용하지 않지만, Week 2 StructuredRequest
    형태로 스케줄 row를 다뤄야 하는 향후 확장(예: 조율 결과를 다시
    구조화된 요청으로 남기는 기능)을 위해 남겨둔 헬퍼입니다.
    """

    return StructuredRequest(
        kind="personal_schedule",
        title=row.get("title"),
        date=row.get("date"),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        members=row.get("attendees") or row.get("members") or [],
        original_text=str(row.get("title") or ""),
    )


_SAFE_ERROR_MESSAGES = {
    "parse_error": "외부 일정 조회 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "invalid_shape": "외부 일정 조회 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "mcp_reported_failure": "외부 일정 조회에 실패했습니다. 잠시 후 다시 시도해주세요.",
    "invalid_rows": "외부 일정 조회 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.",
}
_DEFAULT_SAFE_ERROR_MESSAGE = "외부 일정 조회에 실패했습니다. 잠시 후 다시 시도해주세요."


def _collect_member_schedules(
    *,
    member_names: list[str],
    date_from: str,
    date_to: str,
    personal_schedules: list[dict[str, Any]],
) -> dict[str, Any]:
    """내 일정과 외부 멤버 일정을 같은 row 구조로 합칩니다."""

    external_result = _external_gateway.extract_schedules(member_names, date_from, date_to)
    try:
        external_rows = _parse_mcp_rows(external_result)
    except MCPToolError as exc:
        print(f"[collect_member_schedules] MCP 조회 실패 code={exc.code} detail={exc}")
        safe_message = _SAFE_ERROR_MESSAGES.get(exc.code, _DEFAULT_SAFE_ERROR_MESSAGE)
        return {
            "ok": False,
            "error_code": exc.code,
            "rows": [],
            "schedule_summary": safe_message,
        }

    normalized_date_from, normalized_date_to = normalize_external_schedule_date_bounds(
        member_names, date_from, date_to
    )

    my_rows = [
        {
            "member_name": "나",
            "title": row.get("title"),
            "date": row.get("date"),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "notes": "",
        }
        for row in personal_schedules
        if row.get("date") and normalized_date_from <= row["date"] <= normalized_date_to
    ]

    rows = [*my_rows, *external_rows]

    return {
        "ok": True,
        "rows": rows,
        "schedule_summary": external_schedule_summary(rows),
    }


@tool(args_schema=SearchPreviousConversationsInput)
def search_previous_conversations(
    query: str,
    member_names: list[str] | None = None,
    limit: int = 5,
) -> str:
    """외부 SQLite 데이터베이스에 저장된 이전 대화를 검색합니다. query에는 LLM이 고른 짧은 핵심 명사나 구를 넣습니다."""

    result = _external_gateway.search_conversations(query, member_names, limit)

    try:
        rows = _parse_mcp_rows(result)
    except MCPToolError as exc:
        print(f"[search_previous_conversations] MCP 조회 실패 code={exc.code} detail={exc}")
        return json_payload({"ok": False, "rows": [], "needs_clarification": False})

    distinct_ids = _distinct_conversation_ids(rows)
    if len(distinct_ids) > 1:
        return json_payload({
            "ok": True,
            "ambiguous": True,
            "candidates": [
                {"conversation_id": cid, "title": next(r["title"] for r in rows if r["conversation_id"] == cid)}
                for cid in distinct_ids
            ],
            "instruction": "여러 대화가 검색되었습니다. 사용자에게 어느 대화인지 먼저 확인하세요.",
        })

    return json_payload({"ok": True, "ambiguous": False, "rows": rows})


@tool(args_schema=LoadConversationMessagesInput)
def load_conversation_messages(conversation_id: str) -> str:
    """외부 SQLite 데이터베이스에서 특정 이전 대화의 모든 메시지를 불러옵니다."""

    payload = _external_gateway.load_messages(conversation_id)
    return json_payload(payload)


@tool(args_schema=ExtractSchedulesFromHistoryInput)
def extract_schedules_from_history(member_names: list[str], date_from: str, date_to: str) -> str:
    """외부 SQLite 이전 대화에서 멤버별 일정을 추출합니다."""

    return _external_gateway.extract_schedules(member_names, date_from, date_to)


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

    return _external_gateway.create_shared_schedule(
        member_name=member_name,
        title=title,
        date=date,
        start_time=start_time,
        end_time=end_time,
        notes=notes,
        source_conversation_id=source_conversation_id,
        schedule_id=schedule_id,
    )


@tool(args_schema=DeleteSharedScheduleInput)
def delete_shared_schedule(
    schedule_id: str | None = None,
    source_conversation_id: str | None = None,
) -> str:
    """외부 MCP 공유 일정 저장소에서 일정을 삭제합니다."""

    return _external_gateway.delete_shared_schedule(
        schedule_id=schedule_id, source_conversation_id=source_conversation_id
    )


@tool(args_schema=ListSharedSchedulesInput)
def list_shared_schedules(
    member_names: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source_conversation_id: str | None = None,
    limit: int = 50,
) -> str:
    """외부 MCP 공유 일정 저장소에 등록된 일정을 조회합니다. 필터가 없으면 기본 공유 일정을 반환합니다."""

    return _external_gateway.list_shared_schedules(
        member_names=member_names,
        date_from=date_from,
        date_to=date_to,
        source_conversation_id=source_conversation_id,
        limit=limit,
    )


@tool(args_schema=CollectMemberSchedulesInput)
def collect_member_schedules(member_names: list[str], date_from: str, date_to: str) -> str:
    """내 일정과 다른 사람들의 일정을 MCP SQLite 기록에서 모읍니다."""

    personal_schedules = _personal_schedules_for_current_scope(date_from, date_to)
    result = _collect_member_schedules(
        member_names=member_names,
        date_from=date_from,
        date_to=date_to,
        personal_schedules=personal_schedules,
    )
    return json_payload(result)


def week05_tools() -> list[Any]:
    """4주차까지의 도구에 외부 SQLite/MCP 일정 도구를 누적한 목록입니다."""

    return [
        *week04_tools(),
        search_previous_conversations,
        load_conversation_messages,
        extract_schedules_from_history,
        list_shared_schedules,
        collect_member_schedules,
        create_shared_schedule,
        delete_shared_schedule,
    ]


def week05_system_prompt() -> str:
    """5주차 단일 agent가 따르는 시스템 프롬프트입니다."""

    return join_system_prompt(week05_prompt_parts())


def week05_prompt_parts() -> list[str]:
    """1~5주차 system prompt 조각을 누적합니다."""

    return [
        *week04_prompt_parts(),
        (
            "너는 이제 나(사용자) 뿐 아니라 다른 팀원들의 일정도 함께 조율할 수 있다.\n"
            "- '철수랑 저번에 얘기한 일정 있어?'처럼 특정 인물이나 키워드로 과거 대화를\n"
            "  찾을 때는 search_previous_conversations를 사용한다. 이 tool의 결과에는\n"
            "  needs_clarification 필드가 있는데, 이 값은 tool 내부에서 conversation_id\n"
            "  개수를 세어 이미 계산해둔 것이다. needs_clarification이 true이면\n"
            "  (서로 다른 대화가 여러 건 섞여 있다는 뜻) 반드시 사용자에게 어느 대화를\n"
            "  말하는 것인지 먼저 되묻는다. 임의로 하나를 골라 답하지 않는다.\n"
            "- conversation_id가 정확히 1개로 좁혀졌을 때는, search_previous_conversations의\n"
            "  결과(대화 제목, 짧은 발췌)만으로 질문에 충분히 답할 수 있는지 먼저 판단한다.\n"
            "  '그 얘기 언제였지', '누구랑 얘기한 거였지'처럼 날짜/사람 정도만 필요한 질문은\n"
            "  짧은 결과로 답한다. 반면 '뭐라고 했는지 자세히 말해줘', '그때 정확히 무슨 말\n"
            "  오갔는지 보여줘'처럼 세부 맥락이나 정확한 표현이 필요한 질문은\n"
            "  load_conversation_messages로 전체 메시지를 불러온 뒤 답한다.\n"
            "- 일정을 등록/수정/삭제할 때는 그 일정이 '누구 명의'인지로 tool을 구분한다.\n"
            "  '나'의 일정을 새로 만들 때는 personal_create_schedule을 사용한다. 이 tool로\n"
            "  만든 내 일정은 자동으로 외부 공유 일정 저장소에도 동기화되므로,\n"
            "  create_shared_schedule을 별도로 호출할 필요가 없다.\n"
            "- 반면 '철수', '영희'처럼 나 이외의 외부 멤버 명의로 일정을 직접 등록하거나\n"
            "  갱신해야 할 때는 create_shared_schedule을 사용한다. 이 앱은 철수·영희 같은\n"
            "  외부 멤버의 개인 계정을 갖고 있지 않으므로, personal_create_schedule로는\n"
            "  '나' 이외의 명의로 일정을 만들 수 없다. member_name에는 반드시 그 외부\n"
            "  멤버의 실제 이름을 넣고, '나'로 넣지 않는다.\n"
            "- 이미 등록된 공유 일정 row를 삭제할 때도 마찬가지로 명의를 구분한다.\n"
            "  '나'의 일정을 지울 때는 personal_delete_schedule을 사용한다(자동으로\n"
            "  공유 저장소 복사본도 함께 정리된다). 외부 멤버 명의의 공유 일정 row를\n"
            "  직접 삭제해야 할 때만 delete_shared_schedule을 schedule_id 또는\n"
            "  source_conversation_id로 호출한다.\n"
            "- 사용자가 '철수 이름으로 등록해줘'처럼 명시적으로 외부 멤버 명의를 지정했다면,\n"
            "  결과에서 member_name이 실제로 그 사람 이름으로 등록됐는지 확인하고,\n"
            "  '나'로 등록됐다면 그것은 요청과 다른 결과이므로 그렇게 답하지 않는다."
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