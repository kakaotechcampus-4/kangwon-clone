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


# [2주차 수강생 구현 가이드]
#
# 목표
#   Week 2의 핵심은 사용자의 한국어 자연어 요청이나 Week 1 tool이 만든 JSON payload를
#   일정 앱이 읽을 수 있는 StructuredRequest/StructuredRequestBatch로 바꾸는 것입니다.
#   Week 1이 이미 정해진 인자를 받아 임시 일정을 만들었다면, Week 2는 "내일 오후 3시" 같은
#   자연어와 created_schedule JSON을 날짜/시간/종류/멤버 필드로 구조화합니다.
#   구조화 결과는 아직 SQLite, RAG, 외부 멤버 일정 조율 흐름에 저장하지 않습니다.
#
# 과제 구성
#   - 메인과제: Week 2 agent가 자연어 또는 Week 1 tool JSON을 StructuredRequestBatch로
#     최종 반환하는 세로 슬라이스를 완성합니다.
#   - 추가 과제: 메인과제에서 만든 StructuredRequest 스키마를 Week 3 이상 저장/조율 흐름에서
#     재사용할 수 있도록 bridge 함수를 완성합니다.
#
# 구현 위치와 사용할 코드
#   - 이 파일(student_parts/week02_structure_natural_language_requests.py)의
#     StructuredRequest, StructuredRequestBatch, week02_tools(), week02_prompt_parts(),
#     week02_system_prompt(), build_week02_agent()를 확인합니다.
#   - build_week02_agent()는 langchain.agents.create_agent, fixed/llm.py의 chat_model(),
#     week02_system_prompt(), response_format=StructuredRequestBatch를 사용해 Week 2 agent를 만듭니다.
#   - week02_tools()는 Week 1 도구 목록을 그대로 가져옵니다. Week 2 agent는 개인 일정 생성 요청에서
#     personal_create_schedule이 반환한 created_schedule JSON payload를 읽고
#     response_format=StructuredRequestBatch로 최종 구조화 결과를 확인합니다.
#   - week02_prompt_parts()는 student_parts/week01_wake_up_nana.py의 week01_prompt_parts() 위에
#     Week 2 구조화 지시를 추가합니다.
#   - _coerce_structured_request(), extract_structured_request(), extract_schedule_request()는
#     Week 3 이상에서 재사용되는 구조화 bridge입니다. Week 2 파일에 있지만 Week 2 agent에
#     공개되는 tool은 아닙니다.
#
# 메인과제 구현 대상
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
# 추가 과제 구현 대상
#   1. _coerce_structured_request
#      - LangChain structured output 결과가 이미 StructuredRequest이면 그대로 반환합니다.
#      - dict이면 StructuredRequest.model_validate(...)로 검증해 반환합니다.
#      - 예상한 형태가 아니면 RuntimeError를 발생시켜 잘못된 LLM 응답을 조용히 통과시키지 않습니다.
#
#   2. extract_structured_request
#      - chat_model().with_structured_output(StructuredRequest, method="function_calling")를 사용합니다.
#      - system 메시지에는 join_system_prompt(week02_prompt_parts())를 넣고,
#        user 메시지에는 text를 넣어 structured LLM을 호출합니다.
#      - 자연어 또는 JSON 문자열을 StructuredRequest 하나로 검증/구조화합니다.
#
#   3. extract_schedule_request
#      - extract_structured_request(query) 결과에 ok/tool_name/base_date를 붙입니다.
#      - structured_request에는 model_dump() 결과를 넣고, json.dumps(..., ensure_ascii=False)로 반환합니다.
#      - Week 3 이상 저장 tool이 structured_request 필드를 그대로 받을 수 있게 만듭니다.
#
# StructuredRequest 읽는 법
#   - kind: personal_schedule, group_schedule, todo, reminder, unknown 중 하나입니다.
#   - title/date/start_time/end_time: 일정 앱이 실제 저장이나 생성에 사용할 핵심 필드입니다.
#   - members: 참석자/관련 멤버 list입니다. 모르면 빈 list로 둡니다.
#   - priority/reason/original_text: 할 일 우선순위, 판단 근거, 원문 보존용 필드입니다.
#   - 모르는 값을 억지로 만들지 않는 것이 중요합니다. 확실하지 않으면 None 또는 빈 list가 안전합니다.
#   - date/start_time/end_time은 확실할 때만 YYYY-MM-DD, HH:MM 형식으로 채웁니다.
#
# bridge 동작 기준
#   - 요청이 하나뿐이어도 Week 2 agent의 structured_response에는 StructuredRequest 하나를 담습니다.
#   - 여러 일정/할 일/알림 의도가 한 문장에 섞이면 Week 2 agent에서는 여러 StructuredRequest로 나눕니다.
#   - extract_structured_request()는 bridge 용도라 StructuredRequest 하나만 반환합니다.
#   - Week 1 personal_create_schedule은 이미 분해된 인자로 임시 일정을 생성하고,
#     Week 2 agent와 bridge는 그 JSON payload를 읽어 저장 가능한 구조로 최종 변환한다는 차이를 비교합니다.
#
# 참고 코드
#   - week01_prompt_parts()
#      Week 1 system prompt를 이어받아 Week 2 구조화 지시를 누적할 때 사용합니다.
#   - week01_tools()
#      Week 1 개인 일정 tool 목록입니다. Week 2 agent는 이 tool 결과 JSON을 구조화 근거로 씁니다.
#   - extract_structured_request / extract_schedule_request
#      Week 3 이상에서 DB 저장/조율 tool chain에 쓰는 bridge 코드입니다.
#      query 문자열이 자연어든 Week 1 tool JSON이든, Python rule/parser로 매핑하지 않고
#      structured LLM 호출로 구조화한 뒤 JSON tool payload로 감쌉니다.
#
# 검증 방법
#   - 메인과제: ./run.sh --week2로 실행한 뒤 "다음 주 화요일 오후 3시에 철수랑 회의 잡아줘" 같은
#     문장을 입력합니다. 최종 답변이 StructuredRequestBatch class 형식의 structured_response로
#     나오는지 확인합니다.
#   - 추가 과제: Week 3을 실행한 뒤 trace에서 extract_schedule_request 이후
#     save_structured_request가 호출되는지 봅니다. extract_schedule_request의 반환 JSON에
#     ok/tool_name/base_date/structured_request가 들어 있는지 확인합니다.
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
#
#   - _coerce_structured_request(value)
#     LangChain structured output 결과가 이미 StructuredRequest이면 그대로 쓰고, dict이면 Pydantic 검증을 거쳐
#     StructuredRequest로 바꿉니다. 예상한 형태가 아니면 오류를 내서 잘못된 LLM 응답을 조용히 통과시키지 않습니다.
#
#   - extract_structured_request(text)
#     agent loop를 새로 만들지 않고 chat_model().with_structured_output(...)만 사용해 자연어 또는 JSON 문자열을
#     StructuredRequest로 검증/구조화합니다. Week 3 이상에서 저장/조율 직전 입력을 구조화해야 할 때 재사용하는 bridge 함수입니다.
#
#   - extract_schedule_request(query)
#     Week 3 이상 agent가 저장/조율 전에 호출하는 LangChain bridge tool입니다.
#     extract_structured_request(...) 결과에 ok/tool_name/base_date를 붙여 JSON 문자열로 반환하므로,
#     이후 저장 tool이 structured_request 필드를 그대로 받을 수 있습니다.

 
class StructuredRequest(BaseModel):
    """LLM structured output으로 추출되는 2주차 요청 스키마입니다."""

    kind: RequestKind = Field(description="요청 종류")
    title: str | None = Field(default=None, description="일정 제목")
    date: str | None = Field(default=None, description="YYYY-MM-DD")
    start_time: str | None = Field(default=None, description="HH:MM, '미정'이면 None으로 작성")
    end_time: str | None = Field(default=None, description="HH:MM, '미정'이면 None으로 작성")
    members: list[str] = Field(default_factory=list, description="참석자 목록")
    priority: str | None = Field(default=None, description="할 일 우선순위")
    reason: str | None = Field(default=None, description="요청 근거")
    original_text: str = Field(default="", description="원문")


class StructuredRequestBatch(BaseModel):
    """여러 자연어 의도를 StructuredRequest 목록으로 나누는 메인과제 스키마입니다."""

    requests: list[StructuredRequest] = Field(default_factory=list, description="구조화된 요청 목록")
    base_date: str = Field(default_factory=current_app_date_iso, description="현재 날짜(YYYY-MM-DD)")


def _coerce_structured_request(value: Any) -> StructuredRequest:
    """LangChain structured output 결과를 StructuredRequest로 정규화합니다."""

    # TODO: value가 이미 StructuredRequest이면 그대로 반환하세요.
    # TODO: value가 dict이면 StructuredRequest.model_validate(...)로 검증해 반환하세요.
    # TODO: 예상한 형태가 아니면 RuntimeError를 발생시켜 잘못된 LLM 응답을 조용히 통과시키지 마세요.

    if isinstance(value, StructuredRequest):
        return value
    elif isinstance(value, dict):
        return StructuredRequest.model_validate(value)
    else:
        raise RuntimeError(f"Unexpected structured output: {value}")


def extract_structured_request(text: str) -> StructuredRequest:
    """Week 3 이상에서 agent를 새로 띄우지 않고 자연어를 StructuredRequest로 바꿉니다."""

    # TODO: chat_model().with_structured_output(StructuredRequest, method="function_calling")로 structured LLM을 만드세요.
    # TODO: system 메시지에는 join_system_prompt(week02_prompt_parts())를 넣고, user 메시지에는 text를 넣어 invoke하세요.
    # TODO: LLM 결과를 _coerce_structured_request(...)로 정규화해 StructuredRequest 하나로 반환하세요.

    structured_llm = chat_model().with_structured_output(StructuredRequest, method="function_calling")
    system_prompt = join_system_prompt(week02_prompt_parts())
    response = structured_llm.invoke(messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}])

    return _coerce_structured_request(response) 


@tool
def extract_schedule_request(query: str) -> str:
    """Week 3 이상 agent가 저장/조율 전에 호출하는 구조화 bridge tool입니다."""

    # TODO: extract_structured_request(query)를 호출해 자연어 또는 Week 1 JSON payload를 구조화하세요.
    # TODO: ok/tool_name/base_date/structured_request 키를 가진 dict를 만들고 structured_request에는 model_dump() 결과를 넣으세요.
    # TODO: json.dumps(..., ensure_ascii=False)로 JSON 문자열을 반환하세요.

    structured_request = extract_structured_request(query)

    return json.dumps({
        "ok": True,
        "tool_name": "extract_schedule_request",
        "base_date": current_app_date_iso(),
        "structured_request": structured_request.model_dump()
    }, ensure_ascii=False)


def week02_tools() -> list[Any]:
    """Week 2 agent에 Week 1 도구를 노출해 tool JSON을 structured_response 근거로 씁니다."""

    return week01_tools()


def week02_system_prompt() -> str:
    """2주차 agent가 따르는 시스템 프롬프트입니다."""

    system_prompt = [
        "StructuredRequestBatch에는 요청이 하나뿐이어도 반드시 requests 목록에 StructuredRequest 하나를 담아 반환하세요.",
        "personal_create_schedule tool 결과 JSON의 created_schedule을 읽어 StructuredRequest 필드를 채우세요.",
        "tool 결과의 start_time/end_time이 HH:MM 형식이 아닌 경우('미정' 포함) StructuredRequest의 해당 필드는 None으로 처리하세요.",
    ]

    return join_system_prompt([*week02_prompt_parts(), *system_prompt])


def week02_prompt_parts() -> list[str]:
    """2주차 structured output agent가 따르는 system prompt 조각입니다."""

    return [
        *week01_prompt_parts(),
        "주어진 자연어 요청을 StructuredRequestBatch로 구조화하는 Week 2 agent 역할을 수행합니다.",
        f"현재 날짜는 {current_app_date_iso()}입니다. '이번 주 목요일', '다음 주 월요일' 같은 상대적 날짜 표현은 이 날짜를 기준으로 계산하세요.",
        "자연어 요청을 읽고, StructuredRequest 필드로 구조화하세요.",
        "날짜,시간,참석자는 각각 date, start_time 및 end_time, attendees이며, 명확하지 않으면 None 또는 빈 리스트로 두고 추측하지 마세요.",
        "start_time과 end_time은 반드시 HH:MM 숫자 형식만 허용합니다. '저녁', '오전', '미정' 같은 텍스트는 HH:MM으로 표현할 수 없으므로 None으로 처리하세요.",
        "'~해야겠다', '~해야지', '~할 것 같아' 같은 의지·메모 표현은 일정 생성 요청이 아닙니다. personal_create_schedule tool을 호출하지 말고 kind=todo로 바로 구조화하세요.",
        "요청 종류를 파악할 수 없으면 kind='unknown'으로 처리하세요.",
        "한 메시지에 요청이 여러 개면 각각 별도 StructuredRequest로 만들어 requests 목록에 모두 담으세요.",
        (
            "구조화 예시:\n"
            "  [명확한 경우]\n"
            "  입력: '이번 주 목요일 오후 7시 카테캠 실시간 강의 있어.'\n"
            "  출력: kind=personal_schedule, title=카테캠 실시간 강의, date=2026-07-10, start_time=19:00, members=[], original_text='이번 주 목요일 오후 7시 카테캠 실시간 강의 있어.'\n"
            "  이유: 날짜,시간이 명확하고 참석자가 없으므로 members=[].\n\n"
            "  입력: '다음주 월요일 오후 4시 30분에 교수님과 랩미팅있어.'\n"
            "  출력: kind=personal_schedule, title=랩미팅, date=2026-07-13, start_time=16:30, members=['교수님'], original_text='다음주 월요일 오후 4시 30분에 교수님과 랩미팅있어.'\n"
            "  이유: 날짜,시간,참석자 모두 명확하므로 전부 채움.\n\n"
            "  [불확실한 경우]\n"
            "  입력: '내일 저녁에 운동해야겠다.'\n"
            "  출력: kind=todo, title=운동, date=2026-07-09, start_time=None, end_time=None, members=[], original_text='내일 저녁에 운동해야겠다.'\n"
            "  이유: '저녁'은 HH:MM으로 표현 불가하므로 start_time=None. 의지/메모 표현이므로 todo. tool 호출 없음.\n\n"
            "  입력: '나중에 운동해야겠다.'\n"
            "  출력: kind=todo, title=운동, date=None, start_time=None, end_time=None, members=[], original_text='나중에 운동해야겠다.'\n"
            "  이유: 날짜,시간 정보가 전혀 없으므로 date/start_time/end_time 모두 None."
        ),
        "만약 Week 1 personal_create_schedule tool 결과 JSON을 받았다면, 다시 tool을 호출하지 말고 created_schedule payload를 읽어 StructuredRequestBatch로 변환하세요. ",
        "Week 2에서는 SQLite 저장, RAG, 외부 멤버 일정 조율을 하지 않습니다. ",
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
