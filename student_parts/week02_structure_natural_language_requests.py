from __future__ import annotations

import json
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.tools import tool
from pydantic import BaseModel, Field

from fixed.config import CONFIG
from fixed.llm import chat_model
from fixed.runtime_clock import current_app_date_iso
from student_parts.week01_wake_up_nana import join_system_prompt, week01_prompt_parts, week01_tools


RequestKind = Literal["personal_schedule", "group_schedule", "todo", "reminder", "unknown"]
_WEEK02_AGENT: Any | None = None


# [2주차 1회차 수강생 구현 가이드]
#
# 목표
#   Week 1 tool이 만든 JSON payload나 사용자의 한국어 자연어 요청을 일정 앱이 읽을 수 있는
#   StructuredRequest/StructuredRequestBatch로 바꿉니다. Week 1은 이미 정해진 인자를 받아
#   임시 일정을 만들었다면, Week 2는 그 tool 결과 JSON과 "내일 오후 3시" 같은 자연어를
#   날짜/시간/종류/멤버 필드로 구조화하는 단계입니다. 구조화 결과는 아직 저장하지 않습니다.
#
# 구현 위치와 사용할 코드
#   - 이 파일(student_parts/week02_structure_natural_language_requests.py)의 StructuredRequest 스키마와
#     StructuredRequestBatch, week02_tools(), week02_prompt_parts(), week02_system_prompt(),
#     build_week02_agent()를 확인합니다.
#   - build_week02_agent()는 langchain.agents.create_agent, fixed/llm.py의 chat_model(),
#     week02_system_prompt(), response_format=StructuredRequestBatch를 사용해 Week 2 agent를 만듭니다.
#   - week02_tools()는 Week 1 도구 목록을 그대로 가져옵니다. Week 2 agent는 개인 일정 생성 요청에서
#     personal_create_schedule이 반환한 created_schedule JSON payload를 읽고
#     response_format=StructuredRequestBatch로 최종 구조화 결과를 확인합니다.
#   - week02_prompt_parts()는 student_parts/week01_wake_up_nana.py의 week01_prompt_parts() 위에
#     Week 2 구조화 지시를 추가합니다.
#
# 구현 대상
#   1. StructuredRequest 스키마
#      - kind/title/date/start_time/end_time/members/priority/reason/original_text 필드가
#        이후 Week 3 저장 payload의 기준이 됩니다.
#      - kind는 RequestKind Literal에 들어 있는 값만 허용합니다.
#      - 각 필드에는 LLM structured output이 이해할 수 있도록 한국어 description을 붙입니다.
#
#   2. StructuredRequestBatch 스키마
#      - requests에는 StructuredRequest 목록을 담고, 요청이 하나뿐이어도 list 형태를 유지합니다.
#      - base_date에는 상대 날짜 해석 기준일(current_app_date_iso)을 담습니다.
#
#   3. Week 2 agent 세로 슬라이스
#      - week02_tools()는 Week 1 tool 목록을 그대로 반환합니다.
#      - week02_prompt_parts()와 week02_system_prompt()에는 자연어/Week 1 tool JSON을
#        StructuredRequestBatch로 구조화하라는 지시를 넣습니다.
#      - build_week02_agent()에 response_format=StructuredRequestBatch를 연결해
#        ./run.sh --week2가 동작하게 합니다.
#      - 개인 일정 생성 요청에서는 Week 1 personal_create_schedule tool 결과의 created_schedule JSON을
#        LLM이 읽어 StructuredRequestBatch로 최종 변환하는 흐름을 확인합니다.
#
# StructuredRequest 읽는 법
#   - kind: personal_schedule, group_schedule, todo, reminder, unknown 중 하나입니다.
#   - title/date/start_time/end_time: 일정 앱이 실제 저장이나 생성에 사용할 핵심 필드입니다.
#   - members: 참석자/관련 멤버 list입니다. 모르면 빈 list로 둡니다.
#   - priority/reason/original_text: 할 일 우선순위, 판단 근거, 원문 보존용 필드입니다.
#   - 모르는 값을 억지로 만들지 않는 것이 중요합니다. 확실하지 않으면 None 또는 빈 list가 안전합니다.
#   - date/start_time/end_time은 확실할 때만 YYYY-MM-DD, HH:MM 형식으로 채웁니다.
#
# 참고 코드
#   - week01_prompt_parts()
#      Week 1 system prompt를 이어받아 Week 2 구조화 지시를 누적할 때 사용합니다.
#   - week01_tools()
#      Week 1 개인 일정 tool 목록입니다. Week 2 agent는 이 tool 결과 JSON을 구조화 근거로 씁니다.
#
# 검증 방법
#   ./run.sh --week2로 실행한 뒤 "다음 주 화요일 오후 3시에 철수랑 회의 잡아줘" 같은 문장을 입력합니다.
#   최종 답변이 StructuredRequestBatch class 형식의 structured_response로 나오는지 확인합니다.
#
# 함수별 동작 설명
#   - StructuredRequest
#     Week 2 structured output의 중심 스키마입니다. LLM이 자연어에서 뽑은 요청 종류, 제목, 날짜, 시간,
#     멤버, 우선순위, 근거, 원문을 이 class 필드에 맞춰 반환합니다.
#
#   - StructuredRequestBatch
#     StructuredRequest 여러 개와 base_date를 함께 담는 최종 structured_response 스키마입니다.
#     요청이 하나뿐이어도 requests list 안에 StructuredRequest 하나를 담습니다.
#
#   - week02_tools()
#     Week 1 개인 일정 tool을 그대로 노출합니다. Week 2 agent는 개인 일정 생성 요청에서
#     created_schedule JSON을 structured_response의 근거로 사용할 수 있습니다.
#
#   - week02_system_prompt() / week02_prompt_parts()
#     Week 1 prompt 위에 "자연어를 StructuredRequestBatch로 출력한다"는 Week 2 지시를 누적합니다.
#
#   - build_week02_agent() / build_week_agent()
#     response_format=StructuredRequestBatch가 설정된 agent를 만들고 재사용합니다.
#     build_week_agent()는 실행기가 찾는 표준 entry point입니다.


class StructuredRequest(BaseModel):
    """LLM structured output으로 추출되는 2주차 요청 스키마입니다."""

    kind: RequestKind = Field(
        description="요청 종류(personal_schedule/group_schedule/todo/reminder/unknown 중 하나)"
    )
    title: str | None = Field(default=None, description="일정/할 일 제목. 사용자가 제목을 언급하지 않았다면 None")
    date: str | None = Field(default=None, description="YYYY-MM-DD 형식의 날짜. 사용자가 날짜를 언급하지 않았다면 None")
    start_time: str | None = Field(default=None, description="HH:MM 형식의 시작 시각. 사용자가 시작 시각을 언급하지 않았다면 None")
    end_time: str | None = Field(default=None, description="HH:MM 형식의 종료 시각. 사용자가 종료 시각을 언급하지 않았다면 None")
    members: list[str] = Field(default_factory=list, description="일정을 같이 하는 멤버 리스트. 확실하지 않으면 빈 리스트")
    priority: Literal["low", "high"] | None = Field(
        default=None,
        description=(
            "사용자가 명시적으로 표현한 우선순위. "
            "'급한', '중요한', '꼭', '우선적으로' 등이 있으면 high, "
            "'가볍게', '시간 되면' 등이 있으면 low. "
            "kind와 무관하게, 명시적 표현이 없으면 None."
        ),
    )
    reason: str | None = Field(
        default=None,
        description=(
            "디버깅 참고용 설명 필드. kind 분류 근거를 우선 짧게 적고, "
            "모호해서 None으로 둔 주요 필드가 있다면 그 이유도 함께 적는다. "
            "명확한 요청이면 한 문장으로 제한한다. "
            "이 필드는 저장/실행 로직에서 사용되지 않는, 사람이 참고하는 설명용 필드다."
        ),
    )
    original_text: str = Field(default="", description="사용자가 입력한 원문 텍스트 보존용 필드.")


class StructuredRequestBatch(BaseModel):
    """여러 자연어 의도를 StructuredRequest 목록으로 나누는 2차 과제 스키마입니다."""
    
    requests: list[StructuredRequest] = Field(
        default_factory=list, 
        description="사용자 요청에서 추출된 StructuredRequest 목록. 요청이 하나뿐이어도 리스트에 담는다."
    )
    base_date: str = Field(
        default_factory=current_app_date_iso,
        description="상대 날짜(내일, 다음 주 등) 해석 기준이 되는 오늘 날짜(형식: YYYY-MM-DD)"
    )



def _coerce_structured_request(value: Any) -> StructuredRequest:
    """LangChain structured output 결과를 StructuredRequest로 정규화합니다."""
    
    if isinstance(value, StructuredRequest):
        return value
    elif isinstance(value, dict):
        return StructuredRequest.model_validate(value)
    else:
        raise RuntimeError(f"StructuredRequest 또는 dict가 아닌 값입니다: {type(value)}")


def extract_structured_request(text: str) -> StructuredRequest:
    """Week 3 이상에서 agent를 새로 띄우지 않고 자연어를 StructuredRequest로 바꿉니다."""

    structured_llm = chat_model().with_structured_output(StructuredRequest, method="function_calling")
    
    result = structured_llm.invoke([
        {"role": "system", "content": join_system_prompt(week02_prompt_parts())},
        {"role": "user", "content": text},
    ])

    return _coerce_structured_request(result)   


@tool
def extract_schedule_request(query: str) -> str:
    """Week 3 이상 agent가 저장/조율 전에 호출하는 구조화 bridge tool입니다."""
    
    structured = extract_structured_request(query)

    result = {
        "ok": True,
        "tool_name": "extract_schedule_request",
        "base_date": current_app_date_iso(),
        "structured_request": structured.model_dump(),
    }

    return json.dumps(result, ensure_ascii=False)


def week02_tools() -> list[Any]:
    """Week 2 agent에 Week 1 도구를 노출해 tool JSON을 structured_response 근거로 씁니다."""

    return week01_tools()


def week02_system_prompt() -> str:
    """2주차 agent가 따르는 시스템 프롬프트입니다."""

    return join_system_prompt(week02_prompt_parts())


def week02_prompt_parts() -> list[str]:
    """2주차 structured output agent가 따르는 system prompt 조각입니다."""

    return [
        *week01_prompt_parts(),

        # Week 2 agent 역할과 오늘 날짜(상대 날짜 계산 기준) 안내
        f"너는 사용자의 자연어 요청과 Week 1 tool 결과를 StructuredRequestBatch로 구조화하는 Week 2 agent다. "
        f"오늘 날짜는 {current_app_date_iso()}이다.",

        # 필드 구조화 기본 규칙 + reason 필드의 역할 정의
        "사용자의 요청을 kind, title, date, start_time, end_time, members, priority, reason, original_text 필드로 구조화하라. "
        "확실하지 않은 값은 절대 추측하지 말고 None 또는 빈 리스트로 남겨라. "
        "date/start_time/end_time은 확실할 때만 YYYY-MM-DD, HH:MM 형식으로 채워라. "
        "reason 필드는 이 요청을 해당 kind로 분류한 근거, 또는 members/date/start_time 등 "
        "일부 필드를 확정하지 못하고 None/빈 리스트로 남긴 이유를 자유롭게 설명하는 용도다. "
        "분류와 모든 필드가 명확하다면 reason은 None으로 둔다.",

        # kind(personal_schedule/group_schedule/todo/reminder) 분류 기준
        # 분류는 소재가 아니라 사용자가 사용한 "표현의 형태"로 판단한다.
        "personal_schedule/group_schedule, todo, reminder를 구분하는 기준은 다음과 같다: "
        "① 특정 시각에 실제로 참여하거나 진행해야 하는 일(회의, 약속, 수업 등)은 personal_schedule 또는 group_schedule이다. "
        "② 마감 기한까지 완료하면 되고 그 안에서 언제 처리하든 상관없는 해야 할 일(자료 준비, 보고서 작성, 제출, 복용 등)은 todo다. "
        "③ 참여나 완료가 필요한 행위가 아니라, 특정 시점에 그저 상기시켜 달라는 요청은 reminder다. "
        "분류 기준은 요청의 소재(회의, 약, 보고서 등)가 아니라 사용자가 사용한 표현의 형태다. "
        "'~해야 해', '~해줘(행위 자체를 요청)'처럼 행위를 요청하거나 완료를 의도하는 표현은 todo 또는 schedule이고, "
        "'~하라고 알려줘', '~하는 거 알려줘'처럼 상기만 요청하는 표현만 reminder다. "
        "예를 들어 '회의 잡아줘'는 personal_schedule, "
        "'회의 자료 준비해야 해'는 todo, "
        "'오후 3시에 약 먹어야 해'는 '~해야 해'라는 행위 요청이므로 todo, "
        "'약 먹으라고 알려줘'는 같은 소재(약)라도 '~라고 알려줘'라는 상기 요청이므로 reminder다.",

        # 일정/할 일과 무관한 잡담·질문 처리 (kind='unknown', requests를 빈 리스트로 만들지 않음)
        "사용자의 요청이 일정/할 일과 무관한 잡담이나 질문이라면, kind='unknown'인 StructuredRequest를 "
        "하나 만들어 requests 리스트에 담아라. 이때 title/date/start_time 등은 모두 None 또는 빈 리스트로 두고, "
        "original_text에는 사용자의 원문을 그대로 보존하라. requests를 완전히 빈 리스트로 반환하지 마라.",

        # members: 구체적으로 식별 가능한 이름만 채우고, 모호한 집단 표현은 비워둔다
        "members 필드는 사용자가 실제 이름이나 식별 가능한 대상(예: '철수', '김대표')을 언급했을 때만 채운다. "
        "'팀원', '사람들', '다들'처럼 구체적으로 누구인지 특정할 수 없는 표현은 members에 넣지 않고 빈 리스트로 둔다. "
        "이런 경우 reason 필드에 '참석자가 구체적으로 명시되지 않음(예: 팀원)'과 같이 어떤 표현 때문에 "
        "members를 비워뒀는지 남긴다. original_text에는 원문이 그대로 보존되므로 정보 손실은 아니다.",

        # priority: kind와 무관하게 사용자가 명시적으로 우선순위를 표현했을 때만 채운다.
        # (멘토 피드백 반영) 이전엔 schedule류는 항상 None으로 강제했는데,
        # "시각 순서가 정해지는 것"과 "긴급/중요함"은 별개 문제라는 피드백을 받아
        # kind 제한 없이 명시적 표현 기준으로 통일. unknown만 예외로 항상 None.
        "priority는 사용자가 명시적으로 우선순위를 표현했을 때만 채운다. "
        "'급한', '중요한', '꼭', '우선적으로' 같은 표현이 있으면 high, "
        "'가볍게', '시간 되면', '나중에 해도 되는' 같은 표현이 있으면 low로 채운다. "
        "personal_schedule/group_schedule/todo/reminder 중 어떤 kind든 이 규칙이 동일하게 적용된다. "
        "kind='unknown'은 일정/할 일 자체가 아니므로 priority는 항상 None이다. "
        "명시적 표현이 없으면 항상 None으로 둔다.",

        # 모호한 시간/날짜 표현: 임의로 특정 값 추측하지 말고 None + reason에 근거 남기기
        "사용자가 '오후', '아침', '점심쯤', '다음 주 중에'처럼 구체적이지 않은 시간/날짜 표현을 썼다면, "
        "임의로 특정 시각이나 날짜로 추측해서 채우지 말고 해당 필드(date/start_time/end_time)를 None으로 남겨라. "
        "이때 reason 필드에 어떤 표현 때문에 확정하지 못했는지 간단히 남겨라. "
        "예: '오후에 회의하자'는 start_time=None, reason='오후라는 표현만 있어 정확한 시각 불명'. "
        "반면 '오후 3시'처럼 구체적인 시각이 있으면 정상적으로 start_time을 채운다.",

        # Week 1 tool 호출 결과(JSON)를 다시 tool 호출 없이 읽어 구조화하고,
        # 최종 답변은 StructuredRequestBatch JSON 객체 단 하나만 출력하도록 강제
        # (tool 결과를 답변에 그대로 복사해 JSON이 두 번 겹쳐 파싱 실패하던 버그를 막기 위한 규칙 포함)
        "personal_create_schedule 같은 tool을 호출한 결과(JSON)를 이미 받았다면, "
        "그 tool 결과를 답변에 그대로 복사하거나 반복하지 말고, created_schedule 값만 참고해서 StructuredRequest 필드를 채워라. "
        "최종 답변은 반드시 StructuredRequestBatch 형식의 JSON 객체 단 하나여야 한다. "
        "그 외의 설명, 추가 텍스트, 코드블록(```), 중복된 JSON을 절대 포함하지 마라.",

        # 요청이 하나뿐이어도 항상 requests 리스트 형태를 유지
        "요청이 하나뿐이어도 반드시 StructuredRequestBatch의 requests 리스트 안에 "
        "StructuredRequest 하나를 담아 반환하라.",

        # 이번 주차 구현 범위 제한 (저장/검색/외부 조율은 Week 3 이후)
        "Week 2에서는 SQLite 저장, RAG 검색, 외부 멤버와의 일정 조율을 수행하지 않는다. "
        "오직 구조화된 결과(StructuredRequestBatch)를 반환하는 것까지만 한다.",
    ]


def build_week02_agent() -> object:
    """Week 2 대화에서 structured_response를 직접 반환하는 단일 LangChain agent를 만듭니다."""
    
    if not CONFIG.has_openai_key:
        raise RuntimeError("PROXY_TOKEN이 .env에 필요합니다.")

    global _WEEK02_AGENT
    if _WEEK02_AGENT is None:
        _WEEK02_AGENT = create_agent(
            model=chat_model(),
            tools=week02_tools(),
            response_format=StructuredRequestBatch,
            system_prompt=week02_system_prompt(),
        )

    return _WEEK02_AGENT


def build_week_agent() -> object:
    """active-week registry가 호출하는 표준 Week agent builder입니다."""

    return build_week02_agent()
