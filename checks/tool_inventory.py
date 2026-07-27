"""Tier 1 정적 조립 검사 (docs/ASSIGNMENT_CHECK_DESIGN.md).

LLM을 호출하지 않고, student_parts 각 주차의 weekNN_tools()/weekNN_prompt_parts()
조립 결과만 검사합니다. 검사 항목:
  - 스텁 tool 목록 (정보성 — 실패 아님, 아직 구현 안 된 부분을 보여줄 뿐)
  - 이전 주차엔 정상 구현이던 tool이 이번 주차에서 스텁으로 퇴화했는지 (회귀 — 실패)
  - 같은 주차 tool 목록 안에 이름이 중복되는지 (실패)
  - 구현된(스텁이 아닌) tool 이름이 그 주차 system prompt 문자열에 실제로 언급되는지 (실패)
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
import textwrap
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

WEEK_MODULES = {
    1: "student_parts.week01_wake_up_nana",
    2: "student_parts.week02_structure_natural_language_requests",
    3: "student_parts.week03_build_nanas_logbook",
    4: "student_parts.week04_retrieve_nanas_memory",
}


def _tool_name(item: Any) -> str:
    return getattr(item, "name", getattr(item, "__name__", str(item)))


def _underlying_func(item: Any) -> Any:
    return getattr(item, "func", item)


def _is_stub(item: Any) -> bool:
    """함수 본문이 docstring 다음에 `...` (Ellipsis) 하나뿐이면 스텁으로 판단합니다."""

    func = _underlying_func(item)
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    if not tree.body or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False

    body = tree.body[0].body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]  # docstring 제외

    return (
        len(body) == 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and body[0].value.value is Ellipsis
    )


def inspect_week(week: int) -> dict[str, Any]:
    module = importlib.import_module(WEEK_MODULES[week])
    tools_fn = getattr(module, f"week0{week}_tools")
    prompt_parts_fn = getattr(module, f"week0{week}_prompt_parts")

    tools = tools_fn()
    names = [_tool_name(item) for item in tools]
    stub_by_name = {name: _is_stub(item) for name, item in zip(names, tools)}

    duplicates = sorted({name for name in names if names.count(name) > 1})

    prompt_parts = prompt_parts_fn()
    joined_prompt = " ".join(prompt_parts)
    non_stub_names = [name for name in names if not stub_by_name[name]]
    unmentioned = [name for name in non_stub_names if name not in joined_prompt]

    return {
        "names": names,
        "stub_by_name": stub_by_name,
        "duplicates": duplicates,
        "unmentioned": unmentioned,
    }


def main() -> int:
    failures: list[str] = []
    previous: dict[str, bool] | None = None

    for week in sorted(WEEK_MODULES):
        label = f"week0{week}"
        try:
            info = inspect_week(week)
        except Exception as exc:  # noqa: BLE001 - 리포트용으로 원인을 그대로 보여줘야 함
            print(f"FAIL  {label}: tools()/prompt_parts() 로드 중 예외 발생 -> {type(exc).__name__}: {exc}")
            failures.append(f"{label}: load error")
            previous = None
            continue

        print(f"PASS  {label}: tools()/prompt_parts() 로드 성공 ({len(info['names'])}개 tool)")

        stubs = sorted(name for name, is_stub in info["stub_by_name"].items() if is_stub)
        print(f"INFO  {label}: 스텁 tool = {stubs or '없음'}")

        if info["duplicates"]:
            print(f"FAIL  {label}: tool 이름 중복 = {info['duplicates']}")
            failures.append(f"{label}: duplicate names {info['duplicates']}")
        else:
            print(f"PASS  {label}: tool 이름 중복 없음")

        if previous is not None:
            regressed = sorted(
                name
                for name, is_stub in info["stub_by_name"].items()
                if is_stub and name in previous and not previous[name]
            )
            if regressed:
                print(f"FAIL  {label}: 이전 주차엔 구현이던 tool이 스텁으로 퇴화 = {regressed}")
                failures.append(f"{label}: regression {regressed}")
            else:
                print(f"PASS  {label}: 이전 주차 대비 tool 회귀 없음")

        if info["unmentioned"]:
            print(f"FAIL  {label}: 구현된 tool인데 system prompt에 이름이 언급되지 않음 = {info['unmentioned']}")
            failures.append(f"{label}: unmentioned in prompt {info['unmentioned']}")
        else:
            print(f"PASS  {label}: 구현된 tool 전부 system prompt에 언급됨")

        previous = info["stub_by_name"]

    print()
    if failures:
        print(f"FAILED: {len(failures)}개 체크 실패 -> {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
