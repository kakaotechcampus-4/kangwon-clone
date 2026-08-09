"""Week6 멀티에이전트 - 에이전트 테스트.

실행 (PROXY_TOKEN이 있는 .env 상태에서, run.sh와 같은 파이썬 환경):
  $ python tests/test_week06_agent.py        # pytest 없이 __main__ 러너
  $ python -m pytest tests/test_week06_agent.py -v   # pytest 있으면
"""

from fixed.week_agent_registry import run_active_week_agent

ACTIVE_WEEK = 6
PASS_RATE_RUNS = 3        # LLM은 비용/시간 드니 작게. 신뢰도 원하면 키움.
PASS_RATE_THRESHOLD = 0.8


# ---------------------------------------------------------------------------
# 공통 helper 1: agent 1회 실행 -> trace dict
# ---------------------------------------------------------------------------
def run_agent(query: str) -> dict:
    result = run_active_week_agent(ACTIVE_WEEK, [{"role": "user", "content": query}])
    # result.answer = 자연어 최종답, result.trace = 최상위 trace dict
    return result.trace


# ---------------------------------------------------------------------------
# 공통 helper 2: pass rate 판정
#   멘토 원칙: 1회 pass/fail이 아니라 N번 반복한 통과율로 본다.
#   LLM은 비결정적이라 100%가 아님 -> 임계값 이상이면 통과.
#   check(trace)가 예외를 던져도 그 판(run)은 '실패'로 세고 계속 진행.
#   (goal 루프와 다른 점: '될 때까지'가 아니라 '고정 N번' 돌려 비율 측정)
# ---------------------------------------------------------------------------
def assert_pass_rate(query: str, check, label: str) -> None:
    passed = 0
    for _ in range(PASS_RATE_RUNS):
        try:
            if check(run_agent(query)):
                passed += 1
        except Exception:
            pass  # 이번 판 실패로 카운트
    rate = passed / PASS_RATE_RUNS
    print(f"[{label}] pass rate: {passed}/{PASS_RATE_RUNS} = {rate:.0%}")
    assert rate >= PASS_RATE_THRESHOLD


# ---------------------------------------------------------------------------
# 1) 라우팅: 개인일정 -> nana / 그룹조율 -> kana
# ---------------------------------------------------------------------------
def test_개인일정_요청은_nana로_라우팅된다():
    assert_pass_rate(
        "내일 오후 3시 회의 일정 저장해줘",
        lambda t: t["supervisor_selected_agent"] == "nana_agent",
        "개인->nana",
    )


def test_그룹조율_요청은_kana로_라우팅된다():
    assert_pass_rate(
        "철수랑 영희랑 1시간 회의 시간 잡아줘",
        lambda t: t["supervisor_selected_agent"] == "kana_agent",
        "그룹->kana",
    )


# ---------------------------------------------------------------------------
# 2) tool 호출: 그룹조율은 find_common + decide 를 부른다 (값 X, 존재 in)
# ---------------------------------------------------------------------------
def test_그룹조율은_조율_tool들을_호출한다():
    assert_pass_rate(
        "철수랑 영희랑 1시간 회의 시간 잡아줘",
        lambda t: "find_common_available_slots" in t["inner_tool_names"]
        and "decide_final_slot" in t["inner_tool_names"],
        "그룹-tool호출",
    )


def test_일반질문은_어떤_subagent도_호출하지_않는다():
    assert_pass_rate(
        "안녕? 오늘 기분 어때?",
        lambda t: t["inner_tool_names"] == [],   # 호출 0 = 빈 리스트(None 아님)
        "일반질문-무호출",
    )


# ---------------------------------------------------------------------------
# 3) 구조화 출력: final_slot_payload가 계약 형태로 나온다
#    (현재는 코드가 조립해 결정적이지만, 생성을 LLM에 맡기게 바뀌면 흔들릴 수 있어
#     견고성을 위해 다른 검증과 동일하게 pass rate로 통일)
# ---------------------------------------------------------------------------
def test_그룹조율은_final_slot_payload_구조를_만든다():
    def check(t: dict) -> bool:
        p = t["final_slot_payload"]
        return (
            p is not None
            and all(k in p for k in ("final_slot", "members", "candidate_slots"))
            and len(p["candidate_slots"]) > 0   # A+B 프롬프트 지점
        )

    assert_pass_rate("철수랑 영희랑 1시간 회의 시간 잡아줘", check, "payload구조")


if __name__ == "__main__":
    # pytest 없이도 돌아가게 하는 최소 러너 (assert 기반 self-check)
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            ok += 1
        except Exception:
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{ok}/{len(tests)} pass")
