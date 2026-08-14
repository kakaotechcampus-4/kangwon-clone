"""Week 6 프롬프트-tool 일치 정적 검사 (LLM 호출 없음, 무료·즉시).

멘토 리뷰 1차에서 제안받은 방식을 이 저장소 구조에 맞게 정리했습니다. 검사 항목은
3가지입니다.

1. Kana 프롬프트(`kana_prompt_parts()`)가 언급하는 tool 이름이 전부 `kana_tools()`에
   노출돼 있는지. `kana_prompt_parts()`는 이전 주차를 누적하지 않고 자기 완결적으로
   작성되므로(가이드 요구사항), "언급 vs 노출" 비교가 그대로 성립합니다.
2. Nana 프롬프트(`nana_prompt_parts()`, `week04_prompt_parts()`를 누적)가 언급하는
   tool 이름이 전부 `week04_tools()`(Nana 하위 agent의 실제 tool 목록)에 노출돼
   있는지. Nana의 tool 목록 자체가 `week04_tools()`이므로 이 비교도 유효합니다.
3. `supervisor_tools()`가 정확히 `{nana_agent, kana_agent}` 두 개뿐인지(업무 tool이
   새어 들어오지 않았는지).

**supervisor의 system prompt 전체 텍스트에는 이 "언급 vs 노출" 검사를 적용하지
않습니다.** `week06_prompt_parts()`는 가이드 요구사항에 따라
`week05_prompt_parts()`(→ week04 → … → week01)를 그대로 누적하므로, supervisor의
system prompt 문자열에는 실제로 `add_personal_reference`처럼 supervisor가 절대
직접 호출하지 않는 하위 주차 tool 이름이 대량으로 섞여 들어옵니다. 이건 하위
에이전트가 뭘 하는지 설명하는 문맥일 뿐 "supervisor가 이 tool을 불러야 한다"는
지시가 아니므로, 이 상태를 실패로 잡으면 항상 실패하는 검사가 됩니다(가이드가
요구하는 구조 자체와 충돌). 대신 위 3번 검사(노출된 tool 목록 자체)로 supervisor를
검증합니다.

Nana/Kana 사이의 tool 중복(`extract_schedule_request`가 양쪽에 다 있음)은 이
저장소의 6주차 가이드가 명시적으로 요구하는 구성(Kana도 자연어에서 구조화 필드를
뽑아야 하므로 Week2 tool을 그대로 가져다 씀)이라 실패로 잡지 않고 정보로만
출력합니다.

실행: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week06_prompt_tool_consistency.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import student_parts.week01_wake_up_nana as w1
import student_parts.week02_structure_natural_language_requests as w2
import student_parts.week03_build_nanas_logbook as w3
import student_parts.week04_retrieve_nanas_memory as w4
import student_parts.week05_load_kanas_past_conversations as w5
from student_parts import week06_kanamate_decides_schedule as w6
from student_parts.week04_retrieve_nanas_memory import week04_tools

TOOL_NAME_RE = re.compile(r"[a-z]+(?:_[a-z]+)+")

KNOWN_INTENTIONAL_OVERLAP = {"extract_schedule_request"}


def _mentioned_tool_names(prompt_text: str) -> set[str]:
    return set(TOOL_NAME_RE.findall(prompt_text))


def _is_langchain_tool(obj: object) -> bool:
    return hasattr(obj, "name") and hasattr(obj, "args_schema")


def _all_known_tool_names() -> set[str]:
    """실제로 존재하는(어디에 노출됐는지와 무관한) 모든 @tool 이름 전체 집합입니다.

    노출된 tool 목록(week0N_tools())만 훑으면, "정의는 됐지만 어떤 tools() 목록에도
    없는" 롤백된/미노출 tool(예: find_common_available_slots)이 애초에 이 집합에서
    빠져 "언급 vs 노출" 검사가 그 이름을 무시해버립니다. 그래서 모듈 namespace를
    직접 스캔해 LangChain StructuredTool로 보이는 객체를 전부 모읍니다.
    """

    names: set[str] = set()
    for module in (w1, w2, w3, w4, w5, w6):
        for obj in vars(module).values():
            if _is_langchain_tool(obj):
                names.add(w6.tool_name(obj))
    return names


def check_role_prompt_mentions(role: str, prompt_text: str, exposed: set[str], all_known: set[str]) -> str | None:
    """role의 prompt가 언급하지만 exposed에 없는 (그러나 다른 역할엔 실재하는) tool 이름을 찾습니다."""

    mentioned = _mentioned_tool_names(prompt_text)
    missing = (mentioned - exposed) & all_known
    if missing:
        return f"{role}: 프롬프트가 언급하지만 노출 안 된 tool = {sorted(missing)}"
    return None


def check_supervisor_tool_set() -> str | None:
    exposed = {w6.tool_name(item) for item in w6.supervisor_tools()}
    if exposed != {"nana_agent", "kana_agent"}:
        return f"supervisor: 위임 tool 2개 이외의 tool이 노출됨 = {sorted(exposed)}"
    return None


def check_nana_kana_overlap() -> str | None:
    nana_names = {w6.tool_name(item) for item in week04_tools()}
    kana_names = {w6.tool_name(item) for item in w6.kana_tools()}
    overlap = (nana_names & kana_names) - KNOWN_INTENTIONAL_OVERLAP
    if overlap:
        return f"nana/kana: 의도하지 않은 tool 중복 = {sorted(overlap)}"
    return None


def main() -> int:
    all_known = _all_known_tool_names()
    failures: list[str] = []

    kana_result = check_role_prompt_mentions(
        "kana", " ".join(w6.kana_prompt_parts()), {w6.tool_name(t) for t in w6.kana_tools()}, all_known
    )
    if kana_result:
        failures.append(kana_result)

    nana_result = check_role_prompt_mentions(
        "nana", " ".join(w6.nana_prompt_parts()), {w6.tool_name(t) for t in week04_tools()}, all_known
    )
    if nana_result:
        failures.append(nana_result)

    supervisor_result = check_supervisor_tool_set()
    if supervisor_result:
        failures.append(supervisor_result)

    overlap_result = check_nana_kana_overlap()
    if overlap_result:
        failures.append(overlap_result)

    known_overlap = ({w6.tool_name(t) for t in week04_tools()} & {w6.tool_name(t) for t in w6.kana_tools()}) & KNOWN_INTENTIONAL_OVERLAP
    if known_overlap:
        print(f"INFO  nana/kana: 의도된 공유 tool(가이드 명시) = {sorted(known_overlap)}")

    if failures:
        for line in failures:
            print(f"FAIL  {line}")
        print(f"\nFAILED: {len(failures)}개 불일치")
        return 1

    print("PASS  kana/nana 프롬프트 언급 tool 전부 노출됨, supervisor는 위임 tool 2개뿐, 의도치 않은 tool 중복 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
