"""Week 4 출처별 RAG 조회 테스트 — LLM·ChromaDB·PROXY_TOKEN 없이 결정적으로 검증한다.

Week 3 테스트와 같은 원칙(tests/test_week03_logbook.py):
LLM이 안 끼는 부분은 빠르고 결과가 항상 같아야 한다.
여기서 보는 것은 "코드가 계약대로 정리하는가"이고,
"LLM이 출처에 맞는 tool을 고르는가"는 별도 실험
(docs/week04-query-reliability-testplan.md)에서 통과율로 측정한다.

격리 방법 — Week 3과 seam이 다른 이유
  Week 3 tool들은 매 호출마다 CONFIG.app_db_path를 다시 읽어서, CONFIG를
  임시 경로로 monkeypatch하면 실제 DB를 안 건드렸다.
  Week 4의 REFERENCE_STORE / SQLITE_STORE는 import 시점에 한 번 생성되고
  (게다가 REFERENCE_STORE 생성은 ChromaDB가 필요), tool 함수가 그 전역을 직접 쓴다.
  그래서 전역을 갈아끼우는 대신, store를 인자로 받는 helper
  (search_personal_reference_hits / search_saved_request_rows)에 fake store를
  주입해서 검증한다. 이게 이 파일의 주입 지점이다.

여기서 안 보는 것
  - @tool wrapper 자체: REFERENCE_STORE/SQLITE_STORE 전역(실 ChromaDB/SQLite)을
    타므로 결정적이지 않다. 계약 검증은 helper 층에서 끝난다.
  - search_conversation_messages 계열(추가 과제): 본문이 아직 비어 있다.
    범위 밖으로 뺐으므로 "tool 목록에서 빠졌는지"만 확인한다.

실행:
  uv run pytest tests/test_week04_retrieve.py
"""

from typing import Any

import pytest

from student_parts.week04_retrieve_nanas_memory import (
    safe_limit,
    search_personal_reference_hits,
    search_saved_request_rows,
    week04_tools,
)


# ---------------------------------------------------------------------------
# fake store — helper가 실제로 호출하는 메서드만 흉내 낸다
# ---------------------------------------------------------------------------

class FakeReferenceStore:
    """PersonalReferenceStore.search_personal_references만 대신한다.

    실제 store가 돌려주는 raw hit 모양(reference_store.py 참고:
    id/title/content/tags/distance가 평평하게 들어 있음)을 그대로 흉내 내야,
    helper가 이걸 metadata 구조로 다시 접는 게 진짜로 검증된다.
    """

    def __init__(self, hits: list[dict[str, Any]]):
        self._hits = hits
        self.calls: list[dict[str, Any]] = []  # 인자가 그대로 전달됐는지 확인용

    def search_personal_references(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        self.calls.append({"query": query, "limit": limit})
        return self._hits[:limit]


class FakeSQLiteStore:
    """AppSQLiteStore.search_saved_requests만 대신한다.

    실제 시그니처: search_saved_requests(query, kind=None, limit=5).
    helper는 query/limit만 넘기므로 kind는 기본값을 받는다.
    """

    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self.calls: list[dict[str, Any]] = []

    def search_saved_requests(self, query: str, kind: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        self.calls.append({"query": query, "kind": kind, "limit": limit})
        return self._rows[:limit]


# 실제 store가 돌려주는 raw hit 한 건 (평평한 구조)
RAW_HIT = {
    "id": "ref_focus",
    "title": "집중 회의 선호",
    "content": "오전 10-12시 집중도가 높아 중요한 회의는 오전 중반을 선호한다.",
    "tags": "preference,meeting",
    "distance": 0.21,
}


# ---------------------------------------------------------------------------
# 1) hits 계약 — 평평한 raw hit을 id/content/distance/metadata 구조로 접는다
# ---------------------------------------------------------------------------

def test_hits는_id_content_distance_metadata_구조로_정리된다():
    """LLM이 근거 문서를 바로 읽을 수 있도록 계약된 키가 다 있어야 한다."""
    store = FakeReferenceStore([RAW_HIT])

    hits = search_personal_reference_hits(store, query="회의 선호", top_k=2)

    assert len(hits) == 1
    hit = hits[0]
    assert set(hit) == {"id", "content", "distance", "metadata"}
    assert hit["id"] == "ref_focus"
    assert hit["content"] == RAW_HIT["content"]
    assert hit["distance"] == 0.21
    # 평평하던 title/tags가 metadata 안으로 접혔는지
    assert hit["metadata"] == {"title": "집중 회의 선호", "tags": "preference,meeting"}


def test_top_k가_store_limit으로_그대로_전달된다():
    """helper가 top_k를 store의 limit으로 넘겨야 검색 폭이 tool 뜻대로 정해진다."""
    store = FakeReferenceStore([RAW_HIT, RAW_HIT, RAW_HIT])

    search_personal_reference_hits(store, query="q", top_k=2)

    assert store.calls[0]["limit"] == 2


def test_참고자료_검색_결과가_없으면_빈_리스트다():
    """폴백의 근거: 검색이 비면 지어내지 말고 []를 그대로 올려보내야 한다."""
    store = FakeReferenceStore([])

    assert search_personal_reference_hits(store, query="없는것", top_k=5) == []


# ---------------------------------------------------------------------------
# 2) rows 계약 — SQLite 저장 요청 검색 결과를 그대로 넘긴다
# ---------------------------------------------------------------------------

def test_rows는_store_결과를_그대로_반환한다():
    """rows는 정리보다 통과가 핵심 — store가 준 row 그대로 top-level rows로 나간다."""
    rows = [{"request_id": "req_1", "title": "미용실", "date": "2026-07-21"}]
    store = FakeSQLiteStore(rows)

    result = search_saved_request_rows(store, query="미용실", top_k=3)

    assert result == rows
    # query/limit이 store로 그대로 전달됐는지
    assert store.calls[0] == {"query": "미용실", "kind": None, "limit": 3}


def test_저장_요청_검색_결과가_없으면_빈_리스트다():
    """폴백: 저장된 기록이 없으면 rows=[]가 그대로 올라가야 한다."""
    store = FakeSQLiteStore([])

    assert search_saved_request_rows(store, query="없는것", top_k=3) == []


# ---------------------------------------------------------------------------
# 3) safe_limit — LLM/사용자가 넘긴 top_k를 안전한 범위로 보정
# ---------------------------------------------------------------------------

def test_safe_limit은_1미만을_1로_올린다():
    """0이나 음수가 store로 새면 검색이 조용히 빈 결과를 내 폴백처럼 보인다."""
    assert safe_limit(0) == 1
    assert safe_limit(-5) == 1


def test_safe_limit은_maximum을_넘으면_maximum으로_깎는다():
    assert safe_limit(100, maximum=50) == 50
    assert safe_limit(21, maximum=20) == 20


def test_safe_limit은_경계값을_그대로_통과시킨다():
    """경계 안(1, maximum)은 건드리지 않는다."""
    assert safe_limit(1) == 1
    assert safe_limit(50, maximum=50) == 50


def test_safe_limit은_숫자문자열은_int로_바꾸고_이상한_값은_default로():
    """LLM이 "3" 같은 문자열을 넘겨도 살리되, 못 읽는 값은 default로 떨어뜨린다."""
    assert safe_limit("3") == 3          # 숫자 문자열은 int로
    assert safe_limit(None) == 5         # default=5
    assert safe_limit("셋", default=7) == 7  # 못 읽으면 default


# ---------------------------------------------------------------------------
# 4) week04_tools() — 출처별 tool은 노출, 대화검색은 범위 밖이라 빠져 있어야
# ---------------------------------------------------------------------------

def test_week04_tools에_출처별_RAG_tool_3개가_있다():
    """메인과제로 노출한 tool: 참고자료 추가/검색 + 저장 요청 검색."""
    names = {t.name for t in week04_tools()}

    assert {"add_personal_reference", "search_personal_references", "search_saved_requests"} <= names


def test_week04_tools에_대화검색과_통합검색은_없다():
    """추가 과제(대화 RAG)는 범위 밖으로 뺐다 — 목록에 새어 나오면 안 된다."""
    names = {t.name for t in week04_tools()}

    assert "search_conversation_messages" not in names
    assert "search_nana_memory" not in names


def test_week04_tools는_week03_tool_위에_누적된다():
    """Week 4는 Week 3 도구를 대체가 아니라 누적한다 — 개수가 3주차보다 커야 한다."""
    from student_parts.week03_build_nanas_logbook import week03_tools

    assert len(week04_tools()) == len(week03_tools()) + 3
