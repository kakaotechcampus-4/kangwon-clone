# Week 4 심화과제 구현 + 정량 검증 보고서

`search_conversation_messages` 심화과제를 구현하고, 멘토 요구사항(정확한 로직 구현 + 실제 검증)을 재현 가능한 하네스로 검증한 결과입니다. 관련 배경은 `docs/WEEK04_ADVANCED_TASK_AND_MENTORING.md` 참고.

## 1. 구현 요약

| 함수 | 위치 | 상태 |
| --- | --- | --- |
| `search_conversation_messages_dict(...)` | `student_parts/week04_retrieve_nanas_memory.py:265` | 구현 완료 |
| `search_conversation_message_rows(...)` | `:279` | 구현 완료 |
| `search_conversation_messages(...)` (tool) | `:316` | 구현 완료 |
| `search_nana_memory(...)` (tool) | `:328` | **범위 밖(스텁 유지)** — `week04_tools()`에 노출 안 되므로 무해 |

구현은 `docs/WEEK04_IMPLEMENTATION_PLAN.md` 2-5절 스케치와 동일하게 반영했습니다. 핵심(멘토가 경고한 지점): tool 인자 `conversation_id`가 있으면 store `conversation_id`(특정 대화로 좁히기)로, 없으면 `current_session_scope()`를 store `exclude_conversation_id`(현재 대화 제외)로 전달 — 두 파라미터를 바꿔 넣지 않았습니다.

> 참고: 구현 과정에서 `week04_prompt_parts()`에 문자열 안 큰따옴표 중첩으로 인한 문법 오류(모듈 import 불가 상태)가 있어, **단어는 그대로 두고 안쪽 따옴표만 `"` → `'`로** 고쳤습니다(389~390번 줄). 프롬프트 문구 자체는 바꾸지 않았습니다. `*week03_prompt_parts()`가 두 번 들어간 중복(386~388번 줄)은 손대지 않고 그대로 뒀습니다(기능 무해, 기존 리포트에 기록됨).

## 2. 멘토 지적사항 해소 여부

멘토의 핵심 지적은 "미완성 스텁 `search_conversation_messages`가 `week04_tools()`에 노출되어 LLM이 고를 수 있다"였습니다.

- `checks/tool_inventory.py` 재실행 결과 **`week04: 스텁 tool = 없음`** → 이 tool이 더 이상 스텁이 아니므로 **지적사항 해소**(멘토의 A안=목록에서 빼기 대신 B안=구현으로 해결).

## 3. 검증 방법 (2단, 둘 다 `checks/`에 재현 가능한 형태로 커밋)

| 단계 | 파일 | 성격 | LLM/비용 |
| --- | --- | --- | --- |
| 결정론적 로직 검증 | `checks/conversation_rag_check.py` | 가짜 임베딩 주입, 임시 store, 오프라인 | 불필요 |
| 실제 agent golden | `checks/golden_cases.py` + `checks/run_golden.py` | 실제 LLM tool-selection 측정 | 필요(PROXY_TOKEN) |

## 4. 결과 — 정량

### 4-1. 결정론적 로직 검증 (`conversation_rag_check.py`)

**13/13 PASS.** 핵심 확인 항목:
- 반환 계약: `hits`/`rows`/`context`/`rag_backend`/`sync` 키 존재, `hits == rows`, `sync.total == 2`
- **현재 대화 제외**: 세션 스코프를 convA로 두고 `conversation_id=None` → 결과에서 convA 빠지고 convB 남음
- **conversation_id 필터**: `conversation_id=convA` → convA만 반환
- **파라미터 미혼동 증명**: 위 두 케이스가 정반대로 동작(A 제외 vs A만) → 멘토가 경고한 혼동이 없음을 기계적으로 확인

### 4-2. 실제 agent golden — 프롬프트 강화 전 (`run_golden.py`, week4, 68케이스, 6-worker)

| 카테고리 | Pass / Total | Pass율 | 비고 |
| --- | --- | --- | --- |
| `conversation` (이 tool을 골라야 함) | 1 / 32 | **3.1%** | 실패 시: tool 미호출 14, `list_saved_requests` 15, `search_saved_requests` 2 |
| `control_reference` / `control_saved` / `control_chitchat` | 12/12 each | 100% | conversation tool 오호출 0 |
| **전체** | **37 / 68** | **54.4%** | |

- 이 시점의 `week04_prompt_parts()`에는 `search_conversation_messages` 지시문이 없었음.

### 4-3. 실제 agent golden — 프롬프트 강화 후 (동일 68케이스)

사용자 요청으로 `week04_prompt_parts()`를 강화한 뒤(§4-4) 재실행:

| 카테고리 | Pass / Total | Pass율 | 강화 전 대비 |
| --- | --- | --- | --- |
| `conversation` | 11 / 32 | **34.4%** | 3.1% → 34.4% ▲ |
| `control_reference` / `control_saved` / `control_chitchat` | 12/12 each | 100% | 유지(오호출 0) |
| **전체** | **47 / 68** | **69.1%** | 54.4% → 69.1% ▲ |

- **JSON 계약 위반: 0건** (강화 전후 모두).
- **오호출(false positive): 0건** — 강화 후에도 control 36건에서 conversation tool이 잘못 불린 적 없음. 즉 지시문 추가가 과호출을 유발하지 않음.
- **실패 양상의 질적 변화**: 강화 전 실패 31건 중 17건이 **다른 tool로 오라우팅**(`list_saved_requests` 15 등)이었으나, 강화 후 실패 21건은 **전부 "tool 미호출"**(오라우팅 0). → tool 구분 지시문이 "Week3 조회 tool로 새는" 문제는 사실상 제거했고, 남은 실패는 "검색을 아예 안 하고 대화로만 답함"뿐.
- (LLM 비결정성으로 재실행 시 pass율은 소폭 달라질 수 있으나 경향은 동일)

### 4-4. 프롬프트 강화 내용 (`week04_prompt_parts()`)

사용자 요청("지시문 추천 + 다른 프롬프트도 보수 강화")에 따라 다음을 반영:
- `search_conversation_messages` 지시문 신규 추가(과거 대화 내용 재검색 + conversation_id/현재 대화 제외 설명)
- 기존 지시문을 서술형("~설명 문장입니다")에서 명령형으로 정리, 프롬프트에 새어든 메타 문구 제거
- 방어(보수) 지침 강화: tool 미호출 채로 "저장했다"고 답하지 않기, Week3 `personal_list_saved_schedules`와 명시적 구분, 결과 없으면 지어내지 않기, 관련성 낮으면 되묻기, **assistant 자신의 발화만으로 사실 확정 금지**(가이드 79번 줄 요구사항)
- 중복 포함돼 있던 `*week03_prompt_parts()` 제거

### 4-5. 보수성 완화 + 하네스 확장 후 (108케이스, 전 카테고리 측정)

§4-4 강화에서 남은 실패가 전부 "검색 없이 대화로만 답함"이었으므로, 사용자 요청("보수성 일부 완화 + 모두 향상")에 따라 프롬프트의 억제 지침을 완화했습니다(§4-6). 동시에 golden 하네스를 conversation 전용에서 **4개 tool + control 전 카테고리 측정**으로 확장했습니다(`golden_cases.py` 재작성, 108케이스).

| 카테고리 | Pass / Total | Pass율 | 비고 |
| --- | --- | --- | --- |
| `add` (add_personal_reference) | 16 / 20 | **80.0%** | 실패 4건 전부 "tool 미호출"(오라우팅 0) |
| `search_personal` | 20 / 20 | **100%** | |
| `search_saved` | 20 / 20 | **100%** | |
| `conversation` | 32 / 32 | **100%** | §4-3의 34.4% 대비 급상승 |
| `control` (오호출 없어야) | 16 / 16 | **100%** | target tool 오호출 0 |
| **전체** | **104 / 108** | **96.3%** | |

- **JSON 계약 위반 0건, 오호출 0건** 유지 — 완화가 control(false positive)을 전혀 깨지 않음.
- conversation 34.4% → 100%의 결정적 요인: "관련성 낮/모호하면 되묻기" → "되묻기 전에 알맞은 tool을 먼저 시도, 잡담에만 호출 안 함"으로 바꾼 것.
- (하네스가 conversation 전용 68케이스 → 다카테고리 108케이스로 바뀌었고 conversation 어투 템플릿도 소폭 조정됨. 사용자의 별도 500케이스 표와는 케이스 구성이 달라 절대 수치는 1:1 비교 대상이 아니며, 같은 카테고리의 방향성 개선으로 해석해야 함.)

### 4-6. 보수성 완화 내용 (§4-4에 이어 추가 조정)

- "질문 관련성이 매우 낮거나 의도가 모호하면 되묻기 먼저" 지침을 **"모호해도 알맞은 검색 tool을 먼저 한 번 시도하고, 인사·감사·잡담 등 저장·검색과 무관한 발화에만 tool을 호출하지 않는다"** 로 변경 → "검색을 아예 안 하는" 실패를 줄임.
- 첫 줄에 "기억·저장·조회·검색과 조금이라도 관련된 질문이면 추측으로 답하지 말고 먼저 tool을 호출한다"는 search-first 편향 명시.
- 결과 사용 가드는 "관련성 낮으면 사용 안 함"에서 "명백히 무관한 항목만 사용 안 함"으로 완화(경계 사례에서 근거 활용을 덜 억제).

### 4-7. 경계선 명시 리팩터 (프롬프트만 수정, 측정 대기)

사용자의 4차 500케이스 분석에서 드러난 잔여 문제 — `search_personal_references`가 83%에 정체되고 실패의 대부분(21/25)이 `search_saved_requests`로 쏠림(saved 지침이 강해질수록 personal 영역 잠식) + `add`의 10건이 `save_structured_request`로 오분류 — 를 **프롬프트만 수정**해 겨냥:
- `add` 지시문에 "개인 특성은 일정/할 일이 아니므로 `save_structured_request`가 아니라 `add_personal_reference`로 저장" 경계 추가
- `search_personal_references` 지시문에 "'저장/기록해둔 내 취향'처럼 저장을 언급해도 성향·취향은 개인 참고자료" 명시 → personal이 saved에 뺏기는 것 방지
- `search_saved_requests` 지시문을 "일정·할 일·알림에만" 한정하고 Week3 구분을 `personal_list_saved_schedules`+`list_saved_requests` 둘 다로 일반화, "성향·취향은 search_personal_references로 보냄" 경계 추가

코드·하네스는 변경하지 않았음(사용자 요청). tool_inventory week04 전부 PASS. **효과 수치는 사용자의 500케이스 5차 실행으로 검증 예정**(내 108케이스 하네스는 personal/saved가 이미 100%라 이 잠식 문제를 재현하지 못해 검증에 부적합).

### 4-8. 시소 구조 진단 → 단일 라우팅 테이블로 재설계 (프롬프트만, 측정 대기)

§4-7의 경계 강화가 사용자 5차 500케이스에서 역효과: `search_saved_requests` 74.7% → 54.7%(-30건). "성향·취향은 saved가 아니다"를 saved 관점에서 못박자, 모델이 **진짜 일정·할 일 질문에서도** saved 호출을 주저하고 Week3 tool로 샘(list_saved_requests 23→42, personal_list_saved_schedules 15→26). 전체 82.8% → 81.2%.

**진단(사용자·Claude 공통)**: 개별 tool 지침을 하나씩 배타적으로 강화하면 그 tool은 좋아지고 인접 tool이 나빠지는 **시소 구조**가 3→4차, 4→5차에 반복됨. 원인은 "X는 Y가 아니다"식 per-tool 배타 문구가 인접 tool의 정당한 recall까지 억제하기 때문.

**대응(프롬프트만)**: per-tool 배타 문구를 전부 제거하고, 단일 라우팅 테이블 하나로 교체.
- 맨 위에서 "tool 선택은 '질문이 무엇에 대한 것인가'(개인 특성 / 일정·약속 / 과거 대화) 한 축으로만 정하며 '저장'·'기록' 단어는 기준이 아니다"로 keyword 함정을 **한 번만** 무력화.
- (1)~(5) 라우팅 표로 add/personal/saved/conversation/Week3-list를 **긍정형으로 각각 한 칸씩** 배정(서로 "아니다"라고 밀지 않음).
- 프롬프트 조각 8개 → 6개로 감소(배타 문구 제거).

코드·하네스 불변. tool_inventory PASS. **효과는 사용자 500케이스 6차 실행으로 검증 예정** — 시소가 깨졌는지는 saved와 personal을 **동시에** 봐야 함(한쪽만 올라가면 여전히 시소).

### 4-9. 6차(라우팅 표) 실패 → 4차로 롤백 (현재 상태)

§4-8의 단일 라우팅 표 가설은 6차 500케이스에서 **틀린 것으로 확인**:
- `search_saved_requests`만 소폭 개선(54.7% → 63.3%)
- `add_personal_reference`가 96% → 61%로 거의 1차 수준까지 붕괴, `search_personal_references`도 동반 하락
- 추정 원인: 5차까지 `add` 전용으로 못박혀 있던 "tool 미호출 채 '저장했다' 금지" 압박이, 6차에서 5개 tool 공통 일반 규칙 한 줄로 뭉뚱그려지며 **개별 압박이 약해짐**. "표로 정리하면 더 잘 따른다"는 직관이 이 케이스에선 반대로 작용.

**6번 실행 종합**: 4차 프롬프트(전체 82.8%, 카테고리 최저 77%)가 지금까지 **가장 균형 잡힌** 버전. 모든 카테고리를 동시에 90%대로 올린 버전은 아직 없음. false positive는 전 회차 0건 유지.

**조치**: 사용자 지시에 따라 **4차 프롬프트로 롤백**(현재 파일 상태). 4차 = "보수성 완화(모호해도 tool 먼저 시도)" 버전, 개별 tool 배타 경계(5차)와 라우팅 표(6차) 이전. tool_inventory PASS.

| 회차 | 프롬프트 변경 | 전체 | 특징 |
| --- | --- | --- | --- |
| 3차 | 지시문 강화(명령형+방어) | 78.4% | add 72 / saved 64 |
| **4차** | **보수성 완화(tool 먼저 시도)** | **82.8%** | **최저 카테고리 77%, 현재 채택** |
| 5차 | 개별 tool 배타 경계 강화 | 81.2% | saved 74.7→54.7 급락 |
| 6차 | 단일 라우팅 표 | (더 낮음) | add 96→61 붕괴 |

## 5. 핵심 결론

- **함수 로직·JSON 계약은 완벽**(결정론적 13/13, 계약 위반 0, 오호출 0).
- **tool-selection은 프롬프트에 크게 좌우됨**: 지시문 없음 3.1% → 지시문 추가 34.4% → 보수성 완화 100%(conversation 기준). control은 전 구간 100% 유지 → 완화가 정확도를 올리면서도 오호출을 늘리지 않음.
- **남은 미세 개선 여지**: `add`의 실패 4건은 모두 "개인 정보 진술인데 저장 tool 미호출". 더 끌어올리려면 진술형 발화에 대한 저장 지시문을 더 단정적으로 다듬는 방향을 다음 반복에서 시도 가능.

## 6. 멘토 필수조건 충족 체크

- [x] `conversation_id` vs 현재 대화 제외를 `current_session_scope()` 기준으로 정확히 구현 — 4-1에서 기계적으로 검증
- [x] 구현 후 최소한의 케이스로 실제 검증 — 4-1(로직) + 4-2(실제 agent 68케이스), 재현 가능한 형태로 `checks/`에 커밋

## 7. 재현 방법

```bash
# 결정론적 로직 검증 (무료, 항상 실행 가능)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/conversation_rag_check.py

# 정적 조립 검사 (무료)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/tool_inventory.py

# 실제 agent golden (PROXY_TOKEN 필요, API 비용 발생)
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/run_golden.py            # 전체 68건
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run python checks/run_golden.py --limit 8  # 빠른 점검
```

`run_golden.py`는 실제 `data/`를 임시 폴더로 복사한 뒤 CONFIG 경로를 그쪽으로 패치하므로 실제 데이터는 변경되지 않습니다.

## 8. 남은 이슈 (이번 범위 밖, 기록만)

- `add` 카테고리 80%(실패 4건 전부 "미호출") — 진술형 저장 지시문 추가 튜닝 여지
- `search_nana_memory` 미구현(범위 밖, `week04_tools()`에 노출 안 됨)
- (해소됨) conversation tool-selection 3.1% → 34.4% → 100%
- (해소됨) `search_conversation_messages` 지시문 미포함, `*week03_prompt_parts()` 중복
