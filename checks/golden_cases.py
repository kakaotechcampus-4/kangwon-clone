"""Golden 케이스 정의 (docs/ASSIGNMENT_CHECK_DESIGN.md Tier 2).

Week 4의 4개 tool + control(오호출 측정)의 tool-selection 정확도를 재는 케이스셋입니다.
각 케이스는 템플릿 조합으로 결정론적으로 생성됩니다.

케이스 형식:
    {"category": str, "prompt": str, "expect_tool": str | None}
    - expect_tool 이 있으면: 그 tool 이 호출돼야 pass
    - expect_tool 이 None(control): 아래 TARGET_TOOLS 중 아무것도 호출되지 않아야 pass
"""

from __future__ import annotations

ADD = "add_personal_reference"
SEARCH_PERSONAL = "search_personal_references"
SEARCH_SAVED = "search_saved_requests"
CONVERSATION = "search_conversation_messages"
CONVERSATION_TOOL = CONVERSATION  # 하위 호환(예전 import 이름 유지)

# 이 4개 중 하나라도 호출되면 control 케이스는 fail
TARGET_TOOLS = {ADD, SEARCH_PERSONAL, SEARCH_SAVED, CONVERSATION}

_STATEMENT_TONES = ["{p}", "{p} 기억해둬", "참고로 {p}", "{p}, 알아둬"]
_QUESTION_TONES = ["{p}", "{p}?", "혹시 {p}", "{p} 좀 알려줘"]
_SEARCH_TONES = ["{p}", "{p}?", "혹시 {p}", "{p} 좀"]
_CHITCHAT_TONES = ["{p}", "{p}!", "{p} ㅎㅎ", "{p}~"]

# 개인 정보 진술 → add_personal_reference
_ADD_CORE = [
    "나는 매운 음식을 잘 못 먹어",
    "나는 아침형 인간이야",
    "난 회의는 오전보다 오후가 편해",
    "나는 시끄러운 카페에서는 집중이 안 돼",
    "나는 이메일보다 메신저로 소통하는 게 편해",
]

# 저장된 개인 정보 되묻기 → search_personal_references
_SEARCH_PERSONAL_CORE = [
    "내가 뭘 선호한다고 했지",
    "내 취향에 대해 저장된 거 있어",
    "나에 대해 기억하고 있는 거 알려줘",
    "내가 좋아한다고 한 거 찾아줘",
    "내 선호 정보 뭐 있어",
]

# 저장된 일정/할일/알림 내용 키워드 검색 → search_saved_requests
_SEARCH_SAVED_CORE = [
    "저장된 일정 중에 회의 관련된 거 찾아줘",
    "할 일로 저장한 것 중 보고서 관련 있어",
    "알림으로 저장해둔 것 중 약속 있는지 검색해줘",
    "저장된 기록에서 프로젝트 관련 항목 찾아줘",
    "예약해둔 일정 중 병원 있는지 검색해줘",
]

# 과거 대화 내용 재검색 → search_conversation_messages
_CONVERSATION_CORE = [
    "저번에 우리 무슨 얘기 했었지",
    "예전 대화에서 내가 뭐라고 했는지 찾아봐",
    "지난번 채팅에서 얘기한 내용 다시 보여줘",
    "우리가 이전에 나눈 대화 중에 관련된 게 있었나",
    "예전에 나랑 대화할 때 내가 언급한 거 기억나",
    "이전 대화 기록에서 그 얘기 찾아줘",
    "지난 채팅에서 뭐라고 정리했었지",
    "우리가 저번에 대화한 내용 다시 꺼내줘",
]

# 저장·검색과 무관한 잡담 → 아무 target tool도 불리면 안 됨
_CONTROL_CORE = [
    "안녕 오늘 기분 어때",
    "고마워 도움이 됐어",
    "오늘 날씨 참 좋다",
    "좋은 하루 보내",
]


def _expand(core: list[str], tones: list[str]) -> list[str]:
    return [tone.format(p=base) for base in core for tone in tones]


def build_cases() -> list[dict]:
    cases: list[dict] = []
    for prompt in _expand(_ADD_CORE, _STATEMENT_TONES):
        cases.append({"category": "add", "prompt": prompt, "expect_tool": ADD})
    for prompt in _expand(_SEARCH_PERSONAL_CORE, _QUESTION_TONES):
        cases.append({"category": "search_personal", "prompt": prompt, "expect_tool": SEARCH_PERSONAL})
    for prompt in _expand(_SEARCH_SAVED_CORE, _SEARCH_TONES):
        cases.append({"category": "search_saved", "prompt": prompt, "expect_tool": SEARCH_SAVED})
    for prompt in _expand(_CONVERSATION_CORE, _SEARCH_TONES):
        cases.append({"category": "conversation", "prompt": prompt, "expect_tool": CONVERSATION})
    for prompt in _expand(_CONTROL_CORE, _CHITCHAT_TONES):
        cases.append({"category": "control", "prompt": prompt, "expect_tool": None})
    return cases


CASES = build_cases()
