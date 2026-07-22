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


# [4주차 1회차 수강생 구현 가이드]
#
# 목표
#   Nana가 "내가 적어 둔 참고자료"와 "SQLite에 저장된 일정/할 일 기록"을 구분해서 검색하게 합니다.
#   Week 4의 핵심은 RAG를 하나의 마법 함수로 보지 않고, 데이터 출처별 검색 tool을 분리하는 것입니다.
#
# 구현 위치와 사용할 코드
#   - 이 파일(student_parts/week04_retrieve_nanas_memory.py)의 개인 참고자료 저장/검색 tool과
#     SQLite 저장 요청 검색 tool을 구현합니다.
#   - 개인 참고자료 저장소는 fixed/reference_store.py의 PersonalReferenceStore이며,
#     이 파일 상단의 REFERENCE_STORE가 CONFIG.chroma_dir 기준 인스턴스입니다.
#   - SQLite 저장 요청 검색은 fixed/app_store.py의 AppSQLiteStore를 사용하고,
#     이 파일 상단의 SQLITE_STORE가 CONFIG.app_db_path 기준 인스턴스입니다.
#   - 각 tool 입력은 Pydantic args_schema로 검증하고,
#     search_personal_reference_hits(), search_saved_request_rows()에서 조회 결과를 정리합니다.
#   - tool 함수 add_personal_reference/search_personal_references/search_saved_requests는
#     helper 결과를 json_payload()로 감싼 JSON 문자열로 반환합니다.
#   - top_k/limit 보정은 이 파일의 safe_limit()를 사용해 tool 안에서 처리합니다.
#
# 구현 대상
#   1. add_personal_reference
#      - title/content/tags를 REFERENCE_STORE.add_personal_reference에 넘깁니다.
#      - tags가 None이면 빈 list로 바꿉니다.
#      - 이 tool 안에서 reference_backend와 reference가 있는 JSON payload를 완성합니다.
#
#   2. search_personal_references
#      - query와 top_k로 ChromaDB 개인 참고자료를 검색합니다.
#      - top_k는 이 tool 안에서 안전한 범위로 정리합니다.
#      - course repo 기준 계약에 맞게 top-level {"hits": [...]} JSON을 반환합니다.
#      - hit에는 id, content, distance, metadata(title/tags)가 들어가야 답변 근거로 쓰기 쉽습니다.
#
#   3. search_saved_requests
#      - SQLITE_STORE.search_saved_requests(query, limit)를 호출합니다.
#      - top_k는 이 tool 안에서 안전한 범위로 정리합니다.
#      - 검색 결과가 없으면 rows=[]를 그대로 반환합니다.
#      - course repo 기준 계약에 맞게 top-level {"rows": [...]} JSON을 반환합니다.
#
# 출처 구분
#   search_personal_references는 ChromaDB + OpenAI embedding 기반 reference 검색입니다.
#   search_saved_requests는 SQLite structured_requests/schedules 계열 기록 검색입니다.
#   LLM이 질문 성격에 따라 둘 중 하나 또는 둘 다 선택하도록 prompt가 준비되어 있습니다.
#
# 참고 코드
#   학생 1회차 핵심 구현 대상은 add_personal_reference, search_personal_references,
#   search_saved_requests 3개입니다.
#   week04_tools()는 Week 1-3 도구에 Week 4 RAG 도구를 누적합니다.
#
# 검증 방법
#   참고자료를 추가한 뒤 관련 질문을 입력하고 trace에서 search_personal_references 호출을 확인합니다.
#   저장된 일정/할 일 질문은 search_saved_requests가 호출되는지 확인합니다.
#   결과 JSON의 top-level 키가 각각 hits, rows인지 꼭 확인하세요.
#
# 함수별 동작 설명
#   - _decode_attendees(raw_attendees)
#     SQLite row의 attendees_json 문자열을 list로 바꿉니다. 깨진 JSON이나 list가 아닌 값은 빈 list로 처리합니다.
#
#   - json_payload(payload)
#     tool 응답 dict를 한글이 보존되는 JSON 문자열로 바꿉니다.
#
#   - safe_limit(limit, default, maximum)
#     LLM이나 사용자가 넘긴 limit/top_k 값을 int로 바꾸고 1 이상 maximum 이하로 제한합니다.
#
#   - AddPersonalReferenceInput / SearchPersonalReferencesInput / SearchSavedRequestsInput
#     개인 참고자료 추가, 개인 참고자료 검색, SQLite 저장 요청 검색 tool의 입력 스키마입니다.
#
#   - add_personal_reference_dict(...)
#     PersonalReferenceStore에 참고자료를 저장하고, 어떤 backend에 저장됐는지와 저장된 reference row를 dict로 반환합니다.
#
#   - search_personal_reference_hits(...)
#     vector store 검색 결과를 id/content/distance/metadata 구조로 정리합니다. tool은 이 list를 hits로 감싸 반환합니다.
#
#   - search_saved_request_rows(...)
#     AppSQLiteStore의 저장 요청 검색 결과를 rows 배열로 반환합니다. 일정/할 일/알림 구조화 기록을 찾을 때 사용합니다.
#
#   - add_personal_reference(...)
#     참고자료 추가 tool입니다. title/content/tags를 받아 vector store에 저장하고 JSON 문자열을 반환합니다.
#
#   - search_personal_references(...)
#     개인 참고자료 전용 검색 tool입니다. top-level hits 키를 반환하므로 LLM이 근거 문서를 바로 읽을 수 있습니다.
#
#   - search_saved_requests(...)
#     SQLite에 저장된 structured request/schedule 기록 검색 tool입니다. top-level rows 키를 반환합니다.
#
#
# [4주차 2회차 수강생 구현 가이드]
#
# 목표
#   Nana가 "앱에 저장된 일반 채팅 발화"를 별도 RAG 출처로 검색하게 하고,
#   개인 참고자료, 저장된 일정/할 일, 일반 대화 기록 중 질문에 맞는 tool을 고르게 합니다.
#
# 구현 위치와 사용할 코드
#   - 일반 채팅 발화 검색은 fixed/conversation_rag_store.py의 ConversationRAGStore를 사용하고,
#     이 파일 상단의 CONVERSATION_RAG_STORE가 CONFIG.chroma_dir 기준 인스턴스입니다.
#   - search_conversation_messages_dict(), search_conversation_message_rows()에서 앱 대화 RAG 조회 결과를 정리합니다.
#   - search_conversation_messages는 helper 결과를 json_payload()로 감싼 JSON 문자열로 반환합니다.
#   - search_nana_memory는 이전 버전 호환용 통합 검색 helper입니다.
#   - week04_tools()는 student_parts/week03_build_nanas_logbook.py의 week03_tools() 위에
#     Week 4 RAG tool을 누적해 agent에 공개합니다.
#
# 구현 대상
#   1. search_conversation_messages_dict / search_conversation_message_rows
#      - SQLite에 저장된 앱 대화 메시지를 ConversationRAGStore.sync_from_sqlite(...)로 ChromaDB에 lazy sync합니다.
#      - conversation_id를 명시하지 않으면 현재 대화 범위는 검색에서 제외합니다.
#      - hit에는 conversation_id, role, content 등 대화 근거가 있어야 합니다.
#
#   2. search_conversation_messages
#      - query와 top_k로 앱 대화 발화를 검색합니다.
#      - 반환 JSON에는 hits와 rows에 같은 결과를 넣고, context/rag_backend/sync도 함께 둡니다.
#      - assistant 발화만으로 사실을 확정하지 않도록 prompt와 응답 근거를 분리합니다.
#
#   3. search_nana_memory
#      - 이전 버전 호환용 통합 검색 tool입니다.
#      - 개인 참고자료 hit와 SQLite 일정 chunk를 한 번에 묶어 context 문자열을 만듭니다.
#      - 새 구현의 핵심은 출처별 tool이지만, 기존 테스트/trace 호환을 위해 응답 구조를 유지합니다.
#
#   4. week04_system_prompt / week04_prompt_parts
#      - "참고자료", "저장된 일정/할 일", "일반 채팅 발화"를 서로 다른 출처로 설명합니다.
#      - 질문 성격에 따라 search_personal_references, search_saved_requests,
#        search_conversation_messages 중 맞는 tool을 선택하도록 지시합니다.
#
# 출처 구분
#   search_personal_references는 ChromaDB + OpenAI embedding 기반 reference 검색입니다.
#   search_saved_requests는 SQLite structured_requests/schedules 계열 기록 검색입니다.
#   search_conversation_messages는 SQLite conversations/messages를 대화 단위 청크로 sync해 검색하는 agentic RAG입니다.
#   LLM이 질문 성격에 따라 하나 또는 여러 tool을 선택할 수 있어야 합니다.
#
# 검증 방법
#   일반 채팅 발화 질문을 입력하고 trace에서 search_conversation_messages가 호출되는지 확인합니다.
#   conversation_id가 없을 때 현재 대화가 과거 검색처럼 섞이지 않는지 확인합니다.
#   결과 JSON에 hits, rows, context, rag_backend, sync가 유지되는지 확인합니다.
#
# 함수별 동작 설명
#   - SearchConversationMessagesInput / SearchNanaMemoryInput
#     앱 대화 RAG 검색과 기존 호환용 통합 검색 tool의 입력 스키마입니다.
#
#   - search_conversation_messages_dict(...)
#     SQLite 대화 기록을 ConversationRAGStore에 lazy sync한 뒤 ChromaDB 검색을 수행합니다.
#     현재 대화는 기본적으로 제외해 "방금 한 말"이 과거 검색 결과처럼 섞이지 않게 합니다.
#
#   - search_conversation_message_rows(...)
#     search_conversation_messages_dict(...)에서 hits만 꺼내는 내부 helper입니다.
#
#   - search_conversation_messages(...)
#     앱에 저장된 일반 대화 발화를 검색하는 RAG tool입니다. 일정 DB 검색과 다른 출처임을 context/rag_backend/sync로 함께 보여줍니다.
#
#   - search_nana_memory(...)
#     이전 버전 호환용 통합 검색 tool입니다. 개인 참고자료 hit와 SQLite 일정 chunk를 한 번에 묶어 context 문자열을 만듭니다.
#
#   - week04_tools()
#     Week 3까지의 tool에 Week 4 RAG tool들을 누적해 agent에 공개합니다.
#
#   - week04_system_prompt() / week04_prompt_parts()
#     질문 성격에 따라 reference, saved request, conversation RAG 중 맞는 tool을 고르도록 system prompt를 만듭니다.
#
#   - build_week04_agent() / build_week_agent()
#     Week 1~4 tool을 가진 agent를 만들고 재사용합니다.


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

    # TODO: PersonalReferenceStore.add_personal_reference(...)로 개인 참고자료를 저장하세요.
    
    # 개인 참고자료를 vector store에 추가
    # input: title, content, tags or []
    # output: reference_id, title, content, tags, backend(vector_store, embedding_model, etc)
    saved = reference_store.add_personal_reference(title=title, content=content, tags=tags or [])
    
    # backend 정보 반환 : reference_backend(저장 위치) + reference(저장된 row)
    return {
        "reference_backend": saved.get("backend"),
        "reference": {key: value for key, value in saved.items() if key != "backend"},
    }


def search_personal_reference_hits(
    reference_store: PersonalReferenceStore,
    *,
    query: str,
    top_k: int = 2,
) -> list[dict[str, Any]]:
    """ChromaDB 검색 결과를 tool이 바로 반환하기 쉬운 hit 구조로 정리합니다."""

    # TODO: 개인 참고자료 검색 결과를 id/content/distance/metadata 구조로 정리하세요.
    # query = 검색할 질문, top_k = 반환할 상위 결과 개수
    # results = query와 가까운(distance 작은) 순으로 정렬된 상위 top_k개의 참고자료
    # distance = 질문 벡터와 문서 벡터 사이의 거리 → 작을수록 의미가 유사함
    results = reference_store.search_personal_references(query, limit=top_k)
    return [
        {
            "id": hit.get("id"),
            "content": hit.get("content"),
            "distance": hit.get("distance"),
            "metadata": {"title": hit.get("title", ""), "tags": hit.get("tags", "")}
        }
        for hit in results
    ]


def search_saved_request_rows(
    sqlite_store: AppSQLiteStore,
    *,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """SQLite 저장 요청을 검색하고 실제 검색 결과만 반환합니다."""

    # TODO: AppSQLiteStore.search_saved_requests(...)로 저장 요청을 검색하세요.

    #search_saved_requests: structured_requests의 raw_json/title/reason을 LIKE 키워드 검색, 최신순 top_k개
    # 참고자료는 벡터 검색, 저장 요청은 키워드 검색 - 출처별로 검색 방식이 다름
    return sqlite_store.search_saved_requests(query, limit=top_k)


def search_conversation_messages_dict(
    sqlite_store: AppSQLiteStore,
    conversation_rag_store: ConversationRAGStore,
    *,
    query: str,
    top_k: int = 5,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """SQLite 대화 목록을 lazy sync한 뒤 ChromaDB conversation RAG 결과를 반환합니다."""

    # TODO: SQLite 대화 기록을 ConversationRAGStore에 lazy sync한 뒤 현재 대화를 제외하고 검색하세요.
    
    # 1. lazy sync: SQLite 대화(원본) -> ChromaDB(검색 인덱스)로 신규/변경분만 반영
    sync = conversation_rag_store.sync_from_sqlite(sqlite_store)

    # 2. conversation_id가 없으면 현재 대화(session scope)를 검색에서 제외
    # 방금 한 말이 과거 검색 결과처럼 섞이지 않도록 함
    exclude_conversation_id = None if conversation_id else current_session_scope()

    # 3. 대화 청크 벡터 검색 (제외/특정 대화 지정은 store가 처리)
    hits = conversation_rag_store.search(
        query=query,
        top_k=top_k,
        exclude_conversation_id=exclude_conversation_id,
        conversation_id=conversation_id,
    )

    # 4. 반환: hits/rows(동일) + context(근거 문자열) + rag_backend(검색 backend) + sync(동기화 통계)
    return {
        "hits": hits,
        "rows": hits,
        "context": conversation_rag_store.context_from_hits(hits),
        "rag_backend": conversation_rag_store.backend_info(),
        "sync": sync,
    }


def search_conversation_message_rows(
    sqlite_store: AppSQLiteStore,
    *,
    query: str,
    top_k: int = 5,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """앱 SQLite에 저장된 일반 채팅 대화 청크를 RAG 검색합니다."""

    # TODO: search_conversation_messages_dict(...) 결과에서 hits만 반환하세요.
    
    # dict helper로 검색 후 hits만 추출 (rows / context / rag_backend / sync는 버림)
    # conversation_rag_store는 모듈 인스턴스(CONVERSATION_RAG_STORE) 사용
    return search_conversation_messages_dict(
        sqlite_store,
        CONVERSATION_RAG_STORE,
        query=query,
        top_k=top_k,
        conversation_id=conversation_id,
    )["hits"]


@tool(args_schema=AddPersonalReferenceInput)
def add_personal_reference(title: str, content: str, tags: list[str] | None = None) -> str:
    """
    사용자가 '기억해줘/메모해줘/기록으로 남겨줘'라고 한 날짜 없는 사실·규칙·선호·업무 원칙을 개인 참고자료로 저장합니다.
    일정이 아니라 두고두고 참고할 메모성 정보를 저장할 때 씁니다.
    """

    # TODO: 개인 참고자료를 저장하고 JSON 문자열로 반환하세요.

    # helper로 저장 위임 -> {reference_backend(저장 위치), reference(저장된 자료 row)} dict 반환
    # tags가 None이면 빈 list로 넘김
    payload = add_personal_reference_dict(
        REFERENCE_STORE,
        title=title,
        content=content,
        tags=tags or [],
    )

    # tool 반환은 JSON 문자열 규격 -> json_payload로 dict를 감싸서 JSON 문자열로 변환하여 반환
    return json_payload(payload)


@tool(args_schema=SearchPersonalReferencesInput)
def search_personal_references(query: str, top_k: int = 2) -> str:
    """
    사용자가 저장해 둔 개인 규칙·정책·선호·메모(회의 규칙, 집중 시간대, 점심시간 규칙 등)를 검색합니다.
    '~규칙', '내 선호', '~해도 돼?' 같은 질문에 씁니다.
    """

    # TODO: query/top_k로 개인 참고자료 vector store를 검색하고 top-level hits를 반환하세요.

    # top_k를 안전 범위(1~20)로 보정 후 helper로 검색
    # 검증 스키마(args_schema)인 SearchPersonalReferencesInput의 top_k: int = Field(default=2, ge=1, le=20)
    # -> default=2, maximum=20로 선정
    hits = search_personal_reference_hits(
        REFERENCE_STORE,
        query=query,
        top_k=safe_limit(top_k, default=2, maximum=20),
    )
    
    # tool 반환 : top-level {"hits": [...]} JSON
    return json_payload({"hits": hits})


@tool(args_schema=SearchSavedRequestsInput)
def search_saved_requests(query: str, top_k: int = 3) -> str:
    """
    SQLite에 저장된 일정/할 일/알림을 검색합니다.
    LIKE 키워드 검색이라 query에는 긴 문장 대신 짧은 핵심 명사 하나(예: '보고서', '건강검진')를 넣어야 매칭이 잘 됩니다.
    """

    # TODO: AppSQLiteStore.search_saved_requests(...)로 저장 요청을 검색하고 top-level rows를 반환하세요.
    
    # top_k를 안전 범위로 보정 후 helper로 검색
    # 검증 스키마 SearchSavedRequestsInput의 top_k: int = Field(default=3, ge=1, le=50)
    # -> default=3, maximum=50으로 선정
    limit = safe_limit(top_k, default=3, maximum=50)
    rows = search_saved_request_rows(SQLITE_STORE, query=query, top_k=limit)

    # LIKE 검색이라 긴 문장은 매칭이 잘 되지 않음
    # (1) 검색 결과가 0건 and (2) 검색어가 여러 토큰 -> then 토큰을 하나씩 넣어 처음으로 결과가 나오는 것으로 대체.
    if not rows and len(str(query or "").split()) > 1:
        for token in str(query).split():
            hit = search_saved_request_rows(SQLITE_STORE, query=token, top_k=limit)
            if hit:
                rows = hit
                break

    # tool 반환 : top-level {"rows": [...]} JSON
    return json_payload({"rows": rows})
    


@tool(args_schema=SearchConversationMessagesInput)
def search_conversation_messages(
    query: str,
    top_k: int = 5,
    conversation_id: str | None = None,
) -> str:
    """
    예전에 사용자와 나눈 대화 내용(여행·맛집·루틴 등 저장되지 않은 조언·추천·의견)을 대화 단위 RAG로 검색합니다.
    '저번에/예전에 ~라고 했지', '추천받은' 류 질문에 씁니다.
    query에는 짧은 핵심 명사를 넣습니다.
    """

    # TODO: 앱 SQLite 대화 목록을 대화 단위 ChromaDB RAG로 검색하고 JSON 문자열로 반환하세요.
    # 검증 스키마 SearchConversationMessagesInput의 top_k: int = Field(default=5, ge=1, le=50)
    # -> default=5, maximum=50으로 선정
    payload = search_conversation_messages_dict(
        SQLITE_STORE,
        CONVERSATION_RAG_STORE,
        query=query,
        top_k=safe_limit(top_k, default=5, maximum=50),
        conversation_id=conversation_id
    )
    return json_payload(payload)


@tool(args_schema=SearchNanaMemoryInput)
def search_nana_memory(
    query: str,
    date_from: str | None = None,
    date_to: str | None = None,
    attendee: str | None = None,
    limit: int = 5,
) -> str:
    """개인 참고자료와 SQLite 저장 일정을 한 번에 검색하고 일정 chunk를 반환합니다."""

    # TODO: compatibility 통합 검색이 필요하면 개인 참고자료와 SQLite 일정 chunk를 함께 구성하세요.
    
    # 옛날 방식(현재 함수): 출처를 안 가리고 참고자료와 저장 일정을 모두 탐색한 뒤 한 dict에 몰아 담아 넘김
    # 새 방식: 출처마다 tool을 따로 두어 필요한 것만 탐색할 수 있도록 함
    # 예전 코드가 이 함수를 호출할 수 있어 호환용으로 남김

    # 검증 스키마 SearchNanaMemoryInput의 limit: int = Field(default=5, ge=1, le=20)
    # -> default=5, maximum=20으로 선정
    top_k = safe_limit(limit, default=5, maximum=20)

    # 1. 참고자료 출처: 개인 참고자료 벡터 검색
    reference_hits = search_personal_reference_hits(REFERENCE_STORE, query=query, top_k=top_k)

    # 2. 저장 일정 출처 : SQLite에서 날짜 범위 조회, attendee가 있으면 참석자로 후처리 필터
    #   store의 list_schedules는 attendee를 받지 못하므로, attendees_json을 풀어 _decode_attendees로 직접 거름
    schedules = SQLITE_STORE.list_schedules(limit=top_k, date_from=date_from, date_to=date_to)
    if attendee:
        schedules = [s for s in schedules if attendee in _decode_attendees(s.get("attendees_json"))]

    # 3. 두 출처(참고자료, 저장 일정)를 한 context 문자열로 묶기
    lines = [f"[참고자료] {h['metadata']['title']}: {h['content']}" for h in reference_hits]
    lines += [f"[일정] {s.get('date')} {s.get('start_time')} {s.get('title')}" for s in schedules]
    context = "\n".join(lines)

    # 반환: 합친 context + 원본 검색 결과(참고자료 hit, 일정 목록)
    return json_payload({
        "query": query,
        "context": context,
        "reference_hits": reference_hits,
        "schedules": schedules,
    })


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
        # TODO: Week 4 Nana memory agent system prompt를 자유롭게 추가하세요.

        # 규칙·선호·과거 일정·지난 대화 질문은 기억으로 답하거나 되묻지 말고 반드시 도구로 먼저 확인
        (
            "사용자의 규칙·선호·메모·과거 일정·지난 대화에 관한 질문에는 네 기억으로 답하거나 "
            "'어느 조직/시스템 규칙이냐'고 되묻지 말고, 아래 기준으로 검색 도구를 먼저 호출한 뒤 그 결과로만 답한다."
        ),

        # 출처 선택 기준 (+ 검색어는 짧은 핵심 명사)
        (
            "출처 선택 — "
            "① 개인 규칙·정책·선호·메모('회의실 예약 규칙', '내 집중 시간', '점심시간 규칙', '~해도 돼?')는 search_personal_references. "
            "② 저장한 일정·할 일·알림('저장한 회의', '마감', '알림')은 search_saved_requests(목록이 필요하면 personal_list_saved_schedules). "
            "검색어에는 긴 문장 대신 짧은 핵심 명사 하나를 넣는다(예: '분기 보고서 마감' 대신 '보고서'). "
            "③ 예전 대화로 오간 내용(여행·맛집·루틴 등 저장 안 된 조언·추천·의견; '저번에/예전에/~라고 했지/추천받은')은 search_conversation_messages."
        ),

        # 참고자료 '추가' vs '일정 저장' 구분 (최다 실패 지점)
        (
            "저장 요청 구분 — 날짜·시간이 있는 약속/할 일/알림만 일정으로 저장한다. "
            "날짜 없는 사실·규칙·선호·업무 원칙을 '기억해줘/메모해줘/기록으로 남겨줘/원칙 추가'로 남겨달라고 하면 "
            "일정(save_structured_request)이 아니라 add_personal_reference로 참고자료에 저장한다."
        ),

        # 폴백: 첫 출처가 비면 다른 출처(특히 대화)로 이어 검색, 다 뒤졌을 때만 '없음'
        (
            "가장 맞는 출처를 먼저 검색하고, 결과(hits/rows)가 비면 그대로 '없다'고 하지 말고 "
            "다른 출처(특히 search_conversation_messages)를 이어서 검색한다. 여러 출처를 다 뒤졌을 때만 없다고 답한다."
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
