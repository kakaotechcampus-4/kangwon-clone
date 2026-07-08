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

#1. LLM이 자연어 하나 분석해서 뽑아낸 결과 담음 (ex. 무엇 요청? 언제/몇시/누구랑.. 하나의 스키마)
class StructuredRequest(BaseModel):
    """LLM structured output으로 추출되는 2주차 요청 스키마입니다."""

    kind: RequestKind = Field(
        description=(
            "요청 종류. personal_schedule은 참석자 없는 개인 일정, "
            "group_schedule은 참석자/멤버가 있는 일정, "
            "todo는 특정 날짜/시간이 아니라 처리해야 할 일 자체가 중요한 요청, "
            "reminder는 다른 일정이나 사건을 기준으로 몇 분/시간 전에 알려달라는 요청, "
            "unknown은 위 네 가지로 분류하기 애매하거나 정보가 부족한 요청."
        )
    )
    title: str | None = Field(default=None, description="일정/할 일의 제목. 확실하지 않으면 억지로 만들지 않고 None으로 둔다.")
    date: str | None = Field(default=None, description="관련 날짜, YYYY-MM-DD 형식. 확실하지 않으면 None으로 둔다.")
    start_time: str | None = Field(default=None, description="시작 시각, HH:MM 형식. 정확한 시각을 확신할 수 없으면 지어내지 말고 None으로 둔다.")
    end_time: str | None = Field(default=None, description="종료 시각, HH:MM 형식. 확실하지 않으면 None으로 둔다.")
    members: list[str] = Field(default_factory=list, description="참석자/관련 멤버 목록. 모르면 빈 리스트로 둔다.")
    priority: str | None = Field(default=None, description="할 일의 우선순위(예: low/medium/high). 사용자가 언급하지 않았으면 None.")
    reason: str | None = Field(default=None, description="이 kind와 필드 값으로 판단한 근거를 짧게 설명해줘")
    original_text: str = Field(default="", description="사용자가 입력한 원문 그대로.")


#2. 위 StructuredRequest를 여러개 모아담음.response_format에 실제로 연결
class StructuredRequestBatch(BaseModel):
    """여러 자연어 의도를 StructuredRequest 목록으로 나누는 2차 과제 스키마입니다."""

    requests: list[StructuredRequest] = Field(
        default_factory=list,
        description="사용자 발화에서 뽑아낸 개별 요청 목록. 요청이 하나뿐이어도 리스트에 하나만 담는다.",
    )
    base_date: str = Field(
        default_factory=current_app_date_iso,
        description="'내일', '다음 주 화요일' 같은 상대 날짜를 해석할 때 기준이 되는 오늘 날짜(YYYY-MM-DD).",
    )


def _coerce_structured_request(value: Any) -> StructuredRequest:
    """이후 회차에서 사용할 StructuredRequest 정규화 예약 함수입니다."""

    ...


def extract_structured_request(text: str) -> StructuredRequest:
    """이후 회차에서 사용할 단건 구조화 예약 함수입니다."""

    ...


@tool
def extract_schedule_request(query: str) -> str:
    """이후 회차에서 저장 흐름과 연결할 예약 tool입니다."""

    ...

#3. agent가 쓸 수 있는 도구 목록을 알려줌. week1 일정생성tool 재사용
def week02_tools() -> list[Any]:
    """Week 2 agent에 Week 1 도구를 노출해 tool JSON을 structured_response 근거로 씁니다."""

    return week01_tools()

#5. 4번 지시들을 최종 하나로 완성된 문자열로 합쳐줌. create_agent에 넘겨줄 것들
def week02_system_prompt() -> str:
    """2주차 agent가 따르는 시스템 프롬프트입니다."""

    final_answer_rule = """
    [Week 2 최종 답변 규칙]
    - Week 1의 "결과를 요약해줘" 지시는 이번 주 적용하지 않는다. 최종 메시지는 자연어 없이
      오직 StructuredRequestBatch JSON 하나여야 한다. requests는 요청이 하나여도 리스트로 유지한다.

    [분류]
    - members가 있으면 group_schedule, 없으면 personal_schedule (members 있는데 personal_schedule로 두는 모순 금지).
    - 특정 시각의 약속이 아니라 처리할 일 자체가 핵심이면 todo (예: "발표 자료 마무리해야 해").
    - "OO 몇 분/시간 전에 알려줘"는 reminder. 애매하면 unknown.
    - 한 문장에 요청이 여러 개 섞여 있으면 각각 별도 StructuredRequest로 나눈다.

    [tool 호출]
    - title과 date가 확실한 personal_schedule/group_schedule 생성 요청만 personal_create_schedule을
      먼저 호출해 실제로 저장한 뒤, 그 결과로 필드를 채운다. todo/reminder/unknown에는 create tool을 쓰지 않는다.
    - 조회 요청은 personal_list_schedules, 삭제 요청은 조회 후 personal_delete_schedule을 호출한다.
    - tool 호출용으로(필수 인자라 어쩔 수 없이) 채운 값이라도, 사용자가 말하지 않았다면
      structured_response 필드에는 옮기지 말고 None으로 둔다.

    [필드 값]
    - date/start_time/end_time: 시각을 알 수 있으면(자연어 표현이라도 변환 가능하면 포함, 예: "오후 6시"->"18:00")
      HH:MM/YYYY-MM-DD로 채우고, 시각 자체를 짐작할 수 없을 때만 None으로 둔다. "미정" 같은 기본값을 지어내지 않는다.
    - 비운 필드가 있으면 이유를 reason에 짧게 남긴다. "팀 회의"의 "팀"처럼 제목 속 일반 명사는 members에 넣지 않는다.

    예시:
    - "다음 주 화요일 오후 3시에 철수랑 회의 잡아줘" -> title/date/start_time 확실 -> personal_create_schedule
      먼저 호출 후 kind=group_schedule, start_time="15:00", members=["철수"]
    - "내일 치이카와랑 저녁 약속 잡아줘" -> kind=group_schedule, members=["치이카와"], start_time=None
      (reason: "저녁"만 있고 구체적 시각은 불명)
    - "발표 자료 마무리해야 해" -> kind=todo (약속이 아니라 처리할 일)
    - "회의 잡고 그것도 해야 하는데" -> group_schedule 1개 + unknown 1개로 나눠 requests에 담음
    """

    return join_system_prompt([*week02_prompt_parts(), final_answer_rule])

#4. agent에게 보낼 지시문 조각 모음. 일정 CRUD 규칙 위에 새 지시 (자연어 구조화, tool 재활용) 얹음
def week02_prompt_parts() -> list[str]:
    """2주차 structured output agent가 따르는 system prompt 조각입니다."""

    return [
        *week01_prompt_parts(),
        f"""
        이제부터 너는 사용자의 자연어 요청을 StructuredRequestBatch 형태로 구조화하는 역할도 같이 할거야.
        오늘 날짜는 {current_app_date_iso()}이고, "내일"/"다음 주 화요일" 같은 상대 날짜는 오늘 날짜를 기준으로 계산해줘.
        """,
        """
        사용자 발화를 분석해서 StructuredRequest의 kind(personal_schedule/group_schedule/todo/reminder/unknown),
        title, date, start_time, end_time, members, priority, reason, original_text 필드로 채워줘.
        확실하지 않은 값은 절대 지어내지 말고 None 또는 빈 리스트로 남겨줘.
        한 문장에 요청이 여러 개 섞여 있으면 각각을 별도의 StructuredRequest로 나눠 requests 리스트에 담아줘.
        """,
        """
        Week 1 tool(personal_create_schedule 등)을 호출해서 결과 JSON을 이미 받았다면,
        그 JSON의 created_schedule 값을 그대로 읽어서 구조화하고 같은 tool을 다시 호출하지 마.
        """,
        """
        이번 주(Week 2)에는 SQLite 저장, RAG 검색, 외부 멤버 일정 조율을 하지 않아.
        구조화된 결과를 반환하는 것까지만 이번 주 범위야.
        """,
    ]

#6. 지금까지 만든 (2스키마, tool 목록, sys prompt) 모두 모아 실 동작하는 LangChain agent 객체 하나를 완성
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
