from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from fixed.config import CONFIG
from fixed.conversation_rag_store import ConversationRAGStore
from fixed.llm import chat_model
from fixed.runtime_clock import current_app_date_iso
from fixed.app_store import AppSQLiteStore
from fixed.reference_store import PersonalReferenceStore
from fixed.session_scope import DEFAULT_SESSION_SCOPE, current_session_scope
from student_parts.week01_wake_up_nana import join_system_prompt
from student_parts.week03_build_nanas_logbook import week03_prompt_parts, week03_tools


REFERENCE_STORE = PersonalReferenceStore(CONFIG.chroma_dir)
SQLITE_STORE = AppSQLiteStore(CONFIG.app_db_path)
CONVERSATION_RAG_STORE = ConversationRAGStore(CONFIG.chroma_dir)
_WEEK04_AGENT: Any | None = None


def _decode_attendees(raw_attendees: str | None) -> list[str]:
    try:
        decoded = json.loads(raw_attendees or "[]")
    except Exception:
        return []
    return decoded if isinstance(decoded, list) else []


def json_payload(payload: dict[str, Any]) -> str:
    """도구 반환용 dict를 한글이 깨지지 않는 JSON 문자열로 변환합니다."""

    return json.dumps(payload, ensure_ascii=False)


def safe_limit(limit: int, default: int = 5, maximum: int = 50) -> int:
    """사용자/LLM이 넘긴 limit 값을 안전한 양의 정수 범위로 보정합니다."""

    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


class AddPersonalReferenceInput(BaseModel):
    """개인 참고자료 추가 입력입니다."""

    title: str
    content: str
    tags: list[str] | None = None


class SearchPersonalReferencesInput(BaseModel):
    """개인 참고자료 검색 입력입니다."""

    query: str
    top_k: int = Field(default=2, ge=1, le=20)


class SearchSavedRequestsInput(BaseModel):
    """SQLite 저장 요청 검색 입력입니다."""

    query: str
    top_k: int = Field(default=3, ge=1, le=50)


class SearchConversationMessagesInput(BaseModel):
    """앱 대화 RAG 검색 입력입니다."""

    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    conversation_id: str | None = None


class SearchNanaMemoryInput(BaseModel):
    """Week 4 호환 통합 검색 입력입니다."""

    query: str
    date_from: str | None = None
    date_to: str | None = None
    attendee: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


def add_personal_reference_dict(
    reference_store: PersonalReferenceStore,
    *,
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """개인 참고자료를 vector store에 추가하고 backend 정보를 반환합니다."""

    return reference_store.add_personal_reference(title=title, content=content, tags=tags or [])



def search_personal_reference_hits(
    reference_store: PersonalReferenceStore,
    *,
    query: str,
    top_k: int = 2,
) -> list[dict[str, Any]]:
    """ChromaDB 검색 결과를 tool이 바로 반환하기 쉬운 hit 구조로 정리합니다."""

    raw_hits = reference_store.search_personal_references(query, limit=top_k)
    hits: list[dict[str, Any]] = []
    for hit in raw_hits:
        tags_value = hit.get("tags", "")
        tags_list = tags_value.split(",") if tags_value else []
        hits.append(
            {
                "id": hit.get("id"),
                "content": hit.get("content"),
                "distance": hit.get("distance"),
                "metadata": {"title": hit.get("title", ""), "tags": tags_list},
            }
        )
    return hits


def search_saved_request_rows(
    sqlite_store: AppSQLiteStore,
    *,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """SQLite 저장 요청을 검색하고 실제 검색 결과만 반환합니다."""

    rows = sqlite_store.search_saved_requests(query, limit=top_k)
    return [
        {**row, "members": _decode_attendees(row.get("members_json"))}
        for row in rows
    ]


def search_conversation_messages_dict(
    sqlite_store: AppSQLiteStore,
    conversation_rag_store: ConversationRAGStore,
    *,
    query: str,
    top_k: int = 5,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """SQLite 대화 목록을 lazy sync한 뒤 ChromaDB conversation RAG 결과를 반환합니다."""

    sync_result = conversation_rag_store.sync_from_sqlite(sqlite_store)

    if conversation_id:
        hits = conversation_rag_store.search(
            query=query,
            top_k=top_k,
            conversation_id=conversation_id,
        )
    else:
        hits = conversation_rag_store.search(
            query=query,
            top_k=top_k,
            exclude_conversation_id=current_session_scope(),
        )

    return {
        "hits": hits,
        "context": conversation_rag_store.context_from_hits(hits),
        "rag_backend": conversation_rag_store.backend_info(),
        "sync": sync_result,
    }


def search_conversation_message_rows(
    sqlite_store: AppSQLiteStore,
    *,
    query: str,
    top_k: int = 5,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """앱 SQLite에 저장된 일반 채팅 대화 청크를 RAG 검색합니다."""

    result = search_conversation_messages_dict(
        sqlite_store,
        CONVERSATION_RAG_STORE,
        query=query,
        top_k=top_k,
        conversation_id=conversation_id,
    )
    return result["hits"]

@tool(args_schema=AddPersonalReferenceInput)
def add_personal_reference(title: str, content: str, tags: list[str] | None = None) -> str:
    """개인 참고자료를 ChromaDB에 추가합니다."""

    result = add_personal_reference_dict(REFERENCE_STORE, title=title, content=content, tags=tags)
    backend = result.pop("backend", None)
    return json_payload({"reference_backend": backend, "reference": result})


@tool(args_schema=SearchPersonalReferencesInput)
def search_personal_references(query: str, top_k: int = 2) -> str:
    """개인 참고자료를 ChromaDB와 OpenAI embedding 기반으로 검색합니다."""

    top_k = safe_limit(top_k, default=2, maximum=20)
    hits = search_personal_reference_hits(REFERENCE_STORE, query=query, top_k=top_k)
    return json_payload({"hits": hits})


@tool(args_schema=SearchSavedRequestsInput)
def search_saved_requests(query: str, top_k: int = 3) -> str:
    """SQLite에 저장된 구조화 일정/할 일/알림 row를 검색합니다. query에는 LLM이 고른 일정/할 일/알림 핵심어를 넣습니다."""

    top_k = safe_limit(top_k, default=3, maximum=50)
    rows = search_saved_request_rows(SQLITE_STORE, query=query, top_k=top_k)
    return json_payload({"rows": rows})


@tool(args_schema=SearchConversationMessagesInput)
def search_conversation_messages(
    query: str,
    top_k: int = 5,
    conversation_id: str | None = None,
) -> str:
    """앱 SQLite 대화 목록을 대화 단위 ChromaDB RAG로 검색합니다. query에는 LLM이 고른 짧은 핵심 명사나 구를 넣습니다."""

    top_k = safe_limit(top_k, default=5, maximum=50)
    result = search_conversation_messages_dict(
        SQLITE_STORE,
        CONVERSATION_RAG_STORE,
        query=query,
        top_k=top_k,
        conversation_id=conversation_id,
    )
    hits = result["hits"]
    return json_payload(
        {
            "hits": hits,
            "rows": hits,
            "context": result["context"],
            "rag_backend": result["rag_backend"],
            "sync": result["sync"],
        }
    )


@tool(args_schema=SearchNanaMemoryInput)
def search_nana_memory(
    query: str,
    date_from: str | None = None,
    date_to: str | None = None,
    attendee: str | None = None,
    limit: int = 5,
) -> str:
    """개인 참고자료와 SQLite 저장 일정을 한 번에 검색하고 일정 chunk를 반환합니다."""

    limit = safe_limit(limit, default=5, maximum=20)
    reference_hits = search_personal_reference_hits(REFERENCE_STORE, query=query, top_k=limit)

    if date_from or date_to:
        raw_rows = SQLITE_STORE.list_saved_requests(date_from=date_from, date_to=date_to, limit=limit)
        saved_rows = [
            {**row, "members": _decode_attendees(row.get("members_json"))}
            for row in raw_rows
        ]
    else:
        saved_rows = search_saved_request_rows(SQLITE_STORE, query=query, top_k=limit)

    if attendee:
        saved_rows = [row for row in saved_rows if attendee in row.get("members", [])]

    lines = ["[개인 참고자료]"]
    if reference_hits:
        for hit in reference_hits:
            title = hit["metadata"].get("title", "")
            lines.append(f"- {title}: {hit['content']}")
    else:
        lines.append("- 없음")

    lines.append("[저장된 일정/할 일]")
    if saved_rows:
        for row in saved_rows:
            lines.append(f"- {row.get('title')} ({row.get('date')} {row.get('start_time')})")
    else:
        lines.append("- 없음")

    return json_payload(
        {
            "hits": reference_hits,
            "rows": saved_rows,
            "context": "\n".join(lines),
        }
    )

def week04_tools() -> list[Any]:
    """3주차까지의 도구에 4주차 RAG 도구를 누적한 목록입니다."""

    return [
        *week03_tools(),
        add_personal_reference,
        search_personal_references,
        search_saved_requests,
        search_conversation_messages,
    ]


def week04_system_prompt() -> str:
    """4주차 단일 agent가 따르는 시스템 프롬프트입니다."""

    return join_system_prompt(week04_prompt_parts())


def week04_prompt_parts() -> list[str]:
    """1~4주차 system prompt 조각을 누적합니다."""

    return [
        *week03_prompt_parts(),
        (
            "너는 세 가지 서로 다른 기억 저장소를 구분해서 사용해야 한다.\n"
            "\n"
            "1. 개인 참고자료 (search_personal_references / add_personal_reference)\n"
            "   - 사용자가 '메모해줘', '기억해줘', '참고자료로 남겨줘'처럼 명시적으로 저장을\n"
            "     요청하면 add_personal_reference를 쓴다.\n"
            "   - '내가 뭐라고 메모해뒀지', '저번에 남긴 참고자료 있어?'처럼 과거에 저장한\n"
            "     개인 취향/사실을 찾을 때는 search_personal_references를 쓴다.\n"
            "\n"
            "2. 저장된 일정/할 일/알림 (search_saved_requests)\n"
            "   - 정식으로 구조화되어 등록된 일정/할 일/알림 자체를 다루는 출처다.\n"
            "   - 순수하게 날짜나 기간으로만 조회할 때는(예: '오늘 일정 뭐 있어', '이번 주\n"
            "     할 일 보여줘', '이번 달 일정 브리핑해줘') search_saved_requests가 아니라\n"
            "     Week 3의 personal_list_saved_schedules(date_from, date_to)를 사용한다.\n"
            "     search_saved_requests는 date 컬럼을 비교하는 게 아니라 title/reason/\n"
            "     raw_json 안의 텍스트를 검색하는 tool이라, '이번 주' 같은 표현만으로는\n"
            "     날짜 범위를 정확히 찾을 수 없다.\n"
            "   - 구체적인 제목이 날짜 표현과 함께 언급된 질문은(예: '장어먹은 게\n"
            "     이번주였나', '회의가 다음주 맞나') 날짜부터 좁히지 말고\n"
            "     search_saved_requests로 제목 키워드를 먼저 검색해 결과 row의 date\n"
            "     필드로 답한다. personal_list_saved_schedules로 먼저 좁히면 범위가\n"
            "     틀렸을 때 재검색이 필요해 호출이 낭비된다.\n"
            "   - search_saved_requests는 특정 키워드로 저장 요청을 찾을 때만 사용한다\n"
            "     (예: '회의 관련해서 저장한 거 있어?', '헬스장 예약 저장해뒀나').\n"
            "   - '~일정 언제야', '~저장한 거 있어' 같은 조회 질문에는\n"
            "     extract_schedule_request나 save_structured_request를 호출하지\n"
            "     않는다. 이 두 tool은 새로운 일정/할 일/알림을 등록할 때만 사용한다.\n"
            "   - 일정, 할 일, 알림과 무관한 일반 대화나 잡담에도 extract_schedule_request와\n"
            "     save_structured_request를 호출하지 않는다. 예를 들어 '오늘 점심에 뭐\n"
            "     먹었다', '날씨 좋다', '기분이 좋다'처럼 어떤 시각에 하기로 한 일도,\n"
            "     완료해야 할 일도, 상기받고 싶은 것도 아닌 발화는 그냥 자연스럽게\n"
            "     대화로만 응답하고 tool을 호출하지 않는다. 이런 발화는 별도로 저장하지\n"
            "     않아도 앱 대화 기록에 자동으로 남아 나중에 search_conversation_messages로\n"
            "     찾을 수 있다.\n"
            "3. 일반 대화 기록 (search_conversation_messages)\n"
            "   - '아까 내가 뭐라고 했었지', '저번에 얘기했던 그거' 등 정식 저장이 아니라\n"
            "     단순히 대화 중 지나가듯 언급한 내용을 찾을 때 사용한다.\n"
            "   - 검색된 대화 내용 중 assistant(너 자신)의 과거 발화는 참고만 하고,\n"
            "     그것을 사실 확정 근거로 쓰지 않는다. user의 발화를 우선 근거로 삼는다.\n"
            "\n"
            "구분이 애매하면 이렇게 판단한다:\n"
            "- 질문이 '정식으로 등록/기록했는지'를 묻는 뉘앙스면 saved_requests를 먼저 찾고,\n"
            "  결과가 없으면 search_conversation_messages로 확장해서 다시 찾는다.\n"
            "- 하나의 요청에 여러 출처가 필요하면(예: '일정도 보여주고 관련 메모도 같이') "
            "  해당하는 tool을 모두 호출해서 종합적으로 답한다.\n"
            "- 확실하지 않을 때는 tool을 호출하지 않고 추측해서 답하지 말고, "
            "  가장 가능성 높은 tool부터 시도한다.\n"
            "\n"
            "tool 결과를 근거로 답할 때는 다음 원칙을 반드시 지킨다:\n"
            "- 이번에 호출한 tool의 실제 반환값(hits/rows)에 들어있는 내용만 근거로 삼는다.\n"
            "- 이전 대화에서 기억하는 내용이 있더라도, 이번 tool 결과에 없다면 그것을\n"
            "  이번 답변에 섞어서 마치 이번 검색으로 찾은 것처럼 말하지 않는다.\n"
            "- 검색 결과에 사용자가 찾는 내용이 안 보이면, 무리하게 더 찾으려 하지 말고\n"
            "  관련 자료가 없다고 솔직히 답한다."
        ),
    ]


def build_week04_agent() -> object:
    """Week 1-4 누적 tool 목록을 노출하는 단일 LangChain agent를 만듭니다."""

    if not CONFIG.has_openai_key:
        raise RuntimeError("PROXY_TOKEN이 .env에 필요합니다.")
    global _WEEK04_AGENT
    if _WEEK04_AGENT is None:
        _WEEK04_AGENT = create_agent(
            model=chat_model(),
            tools=week04_tools(),
            system_prompt=week04_system_prompt(),
        )
    return _WEEK04_AGENT


def build_week_agent() -> object:
    """active-week registry가 호출하는 표준 Week agent builder입니다."""

    return build_week04_agent()
