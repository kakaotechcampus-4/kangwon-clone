"""심화과제 결정론적 로직 검증 (docs/WEEK04_ADVANCED_TASK_AND_MENTORING.md B-2 필수조건 1).

LLM 없이(가짜 임베딩 함수 주입) `search_conversation_messages_dict`의 로직을 검증합니다.
멘토가 경고한 "conversation_id(특정 대화로 좁히기) vs 현재 대화 제외"를 서로 바꿔 넣지
않았는지를 임시 SQLite/ChromaDB에 알려진 대화를 심어 직접 확인합니다.

- API 키/비용 불필요, 완전 결정론적, 실제 data/ 는 건드리지 않음(임시 폴더만 사용).
- 검사 항목:
    1. 반환 계약: hits/rows/context/rag_backend/sync 키가 있고 hits == rows
    2. 현재 대화 제외: conversation_id=None + 현재 세션 스코프=convA → 결과에 convA 없음
    3. conversation_id 필터: conversation_id=convA → 결과는 convA만
    4. (2)와 (3)이 서로 다른 결과여야 함 = 두 파라미터가 뒤바뀌지 않았다는 증거
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from fixed.app_store import AppSQLiteStore
from fixed.conversation_rag_store import ConversationRAGStore
from fixed.session_scope import conversation_session_scope
from student_parts.week04_retrieve_nanas_memory import search_conversation_messages_dict


class FakeEmbeddingFunction:
    """OpenAIEmbeddingFunction과 같은 인터페이스의 결정론적 오프라인 임베딩입니다."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def name(self) -> str:
        return "fake_deterministic_check"

    def is_legacy(self) -> bool:
        return True

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in str(text).split():
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            vec[int(digest, 16) % self.dim] += 1.0
        norm = sum(value * value for value in vec) ** 0.5 or 1.0
        return [value / norm for value in vec]

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)


def _conversation_ids(hits: list[dict[str, Any]]) -> set[str]:
    return {str(hit.get("conversation_id") or "") for hit in hits}


def main() -> int:
    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    workdir = Path(tempfile.mkdtemp(prefix="conv_rag_check_"))
    try:
        sqlite_store = AppSQLiteStore(workdir / "app.sqlite3")
        conv_a = sqlite_store.create_conversation("점심 약속 대화")["conversation_id"]
        sqlite_store.append_message(conv_a, "user", "나는 점심 약속은 화요일이나 목요일에 잡는 편이야")
        sqlite_store.append_message(conv_a, "assistant", "네, 점심 약속 요일 선호를 기억해 둘게요")

        conv_b = sqlite_store.create_conversation("운동 루틴 대화")["conversation_id"]
        sqlite_store.append_message(conv_b, "user", "나는 아침에 헬스장 가서 운동하는 걸 좋아해")
        sqlite_store.append_message(conv_b, "assistant", "아침 운동 습관 좋네요")

        rag_store = ConversationRAGStore(
            workdir / "chroma",
            embedding_function=FakeEmbeddingFunction(),
            collection_name="conv_rag_check",
        )

        # (1) 반환 계약 — 세션 스코프 밖(직접 호출)이라 아무것도 제외되지 않음
        result = search_conversation_messages_dict(
            sqlite_store, rag_store, query="점심 약속 요일 운동 습관", top_k=5
        )
        for key in ("hits", "rows", "context", "rag_backend", "sync"):
            check(f"(1) 반환 dict에 '{key}' 키 존재", key in result)
        check("(1) hits == rows (같은 결과)", result.get("hits") == result.get("rows"))
        check("(1) sync 통계에 total 포함", isinstance(result.get("sync"), dict) and "total" in result["sync"])
        check("(1) 두 대화 모두 인덱싱됨(sync.total == 2)", result.get("sync", {}).get("total") == 2)
        check("(1) 제외 없이 두 대화 모두 검색됨", _conversation_ids(result["hits"]) == {conv_a, conv_b})

        # (2) 현재 대화 제외 — 세션 스코프를 convA로 두고 conversation_id 미지정
        with conversation_session_scope(conv_a):
            excluded = search_conversation_messages_dict(
                sqlite_store, rag_store, query="점심 약속 요일 운동 습관", top_k=5
            )
        exclude_ids = _conversation_ids(excluded["hits"])
        check("(2) 현재 대화(convA)가 결과에서 제외됨", conv_a not in exclude_ids)
        check("(2) 다른 대화(convB)는 결과에 남음", conv_b in exclude_ids)

        # (3) conversation_id 필터 — convA로 명시하면 convA만
        filtered = search_conversation_messages_dict(
            sqlite_store, rag_store, query="점심 약속 요일 운동 습관", top_k=5, conversation_id=conv_a
        )
        filter_ids = _conversation_ids(filtered["hits"])
        check("(3) conversation_id=convA → convA만 반환", filter_ids == {conv_a})

        # (4) 두 파라미터가 뒤바뀌지 않았다는 증거: (2)는 A 제외, (3)은 A만 → 정반대
        check(
            "(4) '현재 대화 제외'와 'conversation_id 필터'가 정반대로 동작(파라미터 미혼동)",
            conv_a not in exclude_ids and filter_ids == {conv_a},
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print()
    if failures:
        print(f"FAILED: {len(failures)}개 체크 실패 -> {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
