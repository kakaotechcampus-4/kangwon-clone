# Week 6 테스트 케이스 2200개 (구현 전 준비 완료)

11개 구현 항목 × 200개 = **2200개**를 구현 전에 미리 생성. 스냅샷은 `checks/week06_cases/<item>.jsonl` (11파일).

- 생성기: `checks/week06_cases.py`
- 결정론적 실행: `checks/week06_deterministic.py` (golden 제외)

## 항목별 200개 구성

항목 성격이 달라 200개를 성격별로 나눠 채웠다. **패딩 가짜토큰 없이 전부 만족 가능한 케이스**:

| # | 항목 | 티어 | 결정론적(지금 실행) | golden(배치) |
| --- | --- | --- | --- | --- |
| 1 | `week06_prompt_parts` | 메인 | static 4 (nonempty·accumulate week05·nana_agent/kana_agent 언급) | 196 (라우팅 발화) |
| 2 | `nana_prompt_parts` | 메인 | static 3 | 197 |
| 3 | `kana_prompt_parts` | 메인 | static 4 (nonempty·Kana·kana tool 언급) | 196 |
| 4 | `supervisor_system_prompt` | 메인 | static 3 | 197 |
| 5 | `nana_agent` | 메인 | 0 | 200 (계약키 answer/trace/inner_tool_names) |
| 6 | `kana_agent` | 메인 | 0 | 200 (+final_slot_payload) |
| 7 | `FIND_..._DESCRIPTION` | 추가 | static 6 (candidate_slots·busy_rows·YYYY-MM-DD·HH:MM·decide_final_slot 포함) | 194 |
| 8 | `DECIDE_..._DESCRIPTION` | 추가 | static 4 (final_slot·needs_agent_selection·selected_index) | 196 |
| 9 | `find_common_available_slots_dict` | 추가 | **property 200** | 0 |
| 10 | `find_common_available_slots` | 추가 | **property 200** | 0 |
| 11 | `decide_final_slot` | 추가 | **property 200** | 0 |

- **결정론적 실행 대상: 624개** (static 24 + property 600). 무료·즉시.
- **golden(배치) 대상: 1576개**. 실제 agent 호출 필요 → 구현 후 배치로 실행(멘토 2-2 비용 절제).

## property 200개 설계 (9·10·11 — 멘토 2-4 "인자 무시하면?")

- **9·10 (공통 시간 후보 검증)**: `busy_rows`/`candidate_slots`를 명시로 넘겨(MCP 불필요) 5가지 변형을 순환 — ① busy와 겹치는 후보 → 제외 ② 유효 후보 → 유지 ③ 업무시간 밖 → 제외 ④ 날짜 범위 밖 → 제외 ⑤ 너무 짧음 → 제외. 공통 불변식: `members`에 "나" 포함, top-level 계약키.
- **11 (최종 시간 결정)**: 4변형 — ① 유효 `selected_index` → 확정(`needs_agent_selection=False`) ② 선택 없음 → 보류(True, `final_slot=null`) ③ 범위 밖 index → 보류 ④ `final_slot` 직접 → 확정. top-level `final_slot/reason/candidates/needs_agent_selection` 검사.

## 현재 상태 (구현 전 = spec)

`checks/week06_deterministic.py` 실행 시 **6/624 pass** — 스텁이라 실패가 정상(spec-first). 구현하면:
- 프롬프트/description을 채우면 static 통과
- 슬롯/결정 3함수를 구현하면 property 600 통과 → 결정론적 624/624 목표
- 이후 golden 배치로 라우팅·agent 행동 측정

## 실행

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week06_cases.py          # 2200개 재생성/덤프
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/week06_deterministic.py   # 결정론적 624개
```
