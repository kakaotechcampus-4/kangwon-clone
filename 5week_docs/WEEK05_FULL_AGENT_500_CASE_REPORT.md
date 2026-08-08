# Week 5 실제 Agent 500케이스 테스트 보고서

`student_parts/week05_load_kanas_past_conversations.py`의 메인과제 5개 tool
(`search_previous_conversations`, `load_conversation_messages`,
`extract_schedules_from_history`, `list_shared_schedules`,
`collect_member_schedules`)을 대상으로, mock 없이 **실제 `build_week05_agent()`
+ 실제 LLM(`openai/gpt-4.1-mini`) + 실제 MCP stdio 서브프로세스
(`mcp_server/sqlite_mcp_server.py`)**를 호출하는 500개 테스트 케이스를 실행한
결과입니다. Week4 보고서(`docs/WEEK04_FULL_AGENT_500_CASE_REPORT.md`)와 같은
방법론(격리된 데이터 복사본 + 실제 `run_active_week_agent()` 호출 + trace의
`tool_call` 이벤트 검사)을 그대로 적용했습니다. 추가과제(`create_shared_schedule`,
`delete_shared_schedule`)는 아직 스텁이고 `week05_tools()` 목록에서 제외돼 있어
이번 테스트 범위에서도 제외했습니다.

기존에 `checks/week05_golden.py`로 40케이스 검증(M3)이 이미 있었는데, 그 검증은
"Week5 tool 중 아무거나 호출됐는지"만 이분법으로 봤습니다(`external_people` 83.3%,
`control` 오호출 0/16). 이번 500케이스는 Week4처럼 **tool 하나하나를 개별
카테고리로 나눠** 어떤 tool이 정확히 호출되는지까지 검증했고, 그 결과 40케이스
검증에서는 드러나지 않았던 문제가 여러 건 나왔습니다.

## 1. 방법론

- **실행 경로**: `fixed/week_agent_registry.py::run_active_week_agent(5, messages)`를
  그대로 재사용.
- **데이터 격리**: 실제 `data/chroma`, `data/kanana_app.sqlite3`,
  `data/kanana_external_people.sqlite3`를 임시 폴더에 복사한 뒤
  `CONFIG.chroma_dir`/`app_db_path`/`external_db_path`를 그 복사본으로
  가리키도록 패치하고(`object.__setattr__`) 나서 `student_parts` 모듈을
  import했습니다. Week5 MCP wrapper는 호출마다 `mcp_server/sqlite_mcp_server.py`를
  stdio 서브프로세스로 새로 띄우는데, `fixed/mcp_client.py`가 그 서브프로세스
  환경변수 `KANANA_EXTERNAL_DB_PATH`에 패치된 `CONFIG.external_db_path`를
  넘기므로 서브프로세스도 격리된 복사본만 봅니다. 학생의 실제 `data/`는 이
  테스트로 전혀 변경되지 않았습니다(6절에서 무결성 확인).
- **케이스 구성(총 500개, 6개 카테고리)** — `fixed/external_people_store.py`의
  실제 seed 데이터(멤버 6명: 철수/영희/민준/서연/지훈/하린, 각자 7월 일정 3건,
  대화 6건)를 그대로 활용해 "답이 실제로 존재하는" 질문을 만들었습니다:

  | 카테고리 | 개수 | 기대 tool |
  | --- | --- | --- |
  | `search_previous_conversations` (외부 멤버 과거 대화 검색) | 90 | `search_previous_conversations` |
  | `load_conversation_messages` (특정 대화 전체 메시지 조회, conversation_id 명시) | 60 | `load_conversation_messages` |
  | `extract_schedules_from_history` (외부 멤버 일정/바쁜시간 추출) | 90 | `extract_schedules_from_history` |
  | `list_shared_schedules` (공유 일정 저장소 조회) | 80 | `list_shared_schedules` |
  | `collect_member_schedules` (내 일정+외부 멤버 일정 합치기) | 90 | `collect_member_schedules` |
  | control(순수 개인 용무/잡담, Week5 tool 불필요) | 90 | 없음 |

  `load_conversation_messages`는 자연어만으로는 실제 `conversation_id`(예:
  `ext_cs`)를 알 수 없어서, "conversation_id가 ext_cs인 대화 전체 보여줘"처럼
  ID를 프롬프트에 직접 명시하는 방식으로 만들었습니다 — 다소 부자연스럽지만
  이 tool을 단독으로 검증할 수 있는 유일한 방법입니다(2-2절에서 이 설계의
  한계를 다시 짚습니다).
- **동시 실행**: `ThreadPoolExecutor(max_workers=6)`. 총 소요 시간
  **4,570초(약 76분)** — Week4(초당 임베딩 API 호출)보다 훨씬 오래 걸렸는데,
  Week5는 호출마다 MCP stdio 서브프로세스를 새로 띄우기 때문입니다(3절에서
  이로 인한 심각한 지연 이슈를 다룹니다).
- **판정 기준**: Week4와 동일 — 카테고리별 기대 tool이 `tool_call` 이벤트에
  있으면 pass, control은 5개 대상 tool 중 어느 것도 없으면 pass.

## 2. 결과 요약

| 카테고리 | Pass / Total | Pass율 |
| --- | --- | --- |
| `search_previous_conversations` | 62 / 90 | **68.9%** |
| `load_conversation_messages` | 30 / 60 | **50.0%** |
| `extract_schedules_from_history` | 0 / 90 | **0.0%** |
| `list_shared_schedules` | 78 / 80 | **97.5%** |
| `collect_member_schedules` | 86 / 90 | **95.6%** |
| control (false-positive 없음 확인) | 90 / 90 | **100.0%** |
| **전체** | 346 / 500 | **69.2%** |

- 예외(크래시)·`trace_error`: **0/500** — Week4와 동일하게, 호출된 tool의 실행
  자체는 한 번도 실패하지 않았습니다.
- control false positive: **0/90** — 순수 개인 용무·잡담에서 Week5 tool이
  잘못 호출된 사례는 없었습니다. 기존 40케이스 golden 결과(오호출 0/16)와
  일치합니다.
- latency: 중앙값 13.9s / 평균 54.8s / 최대 **3317.1s(약 55분)**. 평균이
  중앙값보다 훨씬 큰 건 아래 3-2절의 심각한 이상치 때문입니다.

## 3. 발견된 문제

### 3-1. [Critical] `extract_schedules_from_history`가 90건 전부(0%) 호출되지 않음

`search_previous_conversations`/`load_conversation_messages`와 달리, 이 tool은
**단 한 번도 직접 호출되지 않았습니다.** 실패 90건의 구성:

- 76건: `collect_member_schedules` 호출
- 8건: `personal_list_schedules` 호출 (Week1/3 계열, 내 일정만 봄)
- 6건: `personal_list_saved_schedules` 호출 (Week3, 내 일정만 봄)

`collect_member_schedules`가 내부적으로 `extract_schedules_from_history`를
호출하므로(`_collect_member_schedules` 참고) **최종 답변은 대체로 맞게
나옵니다** — 예를 들어 "철수 7월 일정 좀 뽑아줘"에 대해 `collect_member_schedules`가
불려도 철수의 일정 자체는 결과에 들어 있습니다. 다만 이 tool은 "나"의 일정도
함께 SQLite에서 읽어와 rows에 섞기 때문에, "철수만 궁금한" 질문에도 불필요하게
"나"의 일정 조회가 같이 실행됩니다. 더 중요한 건, **가이드가 두 tool을 별도
메인과제 항목으로 나눠뒀는데 실제로는 `extract_schedules_from_history`가
독립적으로 선택되는 경로가 프롬프트상 존재하지 않는다는 점**입니다 —
`week05_prompt_parts()`의 라우팅 문장 (3)번("외부 멤버의 일정·바쁜 시간을
뽑으려면 → extract_schedules_from_history")과 별개 문장으로 (2)번
collect_member_schedules 안내도 있는데, 실제 LLM은 "외부 멤버 일정" 관련
질문을 거의 전부 후자로 흡수해버립니다.

### 3-2. [Critical, 신뢰성] `collect_member_schedules` 동시 호출 시 최대 55분까지 멈춤

latency 상위 5건이 전부 `collect_member_schedules`이고, 값이 비정상적으로
큽니다:

```
CM031  3317.09s
CM035  3316.40s
CM034  3315.76s
CM032  3313.67s
CM029  3293.58s
```

5건 모두 **거의 같은 시각에 시작해 거의 같은 시각에(3293~3317초 부근) 동시에
끝났습니다** — 실제로 실행 중 콘솔에서도 300~350번째 케이스 구간에서 진행이
55분간 멈춘 것처럼 보이는 현상을 직접 관찰했습니다. 예외는 발생하지 않고
결국 정상 완료됐다는 점에서 크래시가 아니라 **일시적 교착(deadlock)에 가까운
지연**으로 보입니다.

가능한 원인: `collect_member_schedules`는 내부에서 `call_external_tool_payload`로
MCP 서브프로세스를 한 번 더 호출합니다(`fixed/mcp_client.py::_run_coroutine_sync`가
스레드마다 새 asyncio 이벤트 루프를 열어 subprocess를 스폰). `ThreadPoolExecutor(max_workers=6)`
환경에서 여러 워커가 동시에 `collect_member_schedules`를 호출하면, 각각이
독립적으로 subprocess를 스폰하려 시도하면서 Windows의 프로세스 생성/파이프
자원에 경합이 생겨 일부 호출이 장시간 블록되는 것으로 추정됩니다. 정확한
근본 원인은 이번 조사로 확정하지 못했고, 재현하려면 `collect_member_schedules`만
동시성을 올려 반복 실행해봐야 합니다.

**왜 심각한가**: pass/fail 판정에는 영향이 없었지만(결국 성공), 실제 서비스에서
여러 사용자가 동시에 "일정 모아줘" 요청을 하면 **응답이 최대 수십 분간 멈출
수 있다는 뜻**입니다. tool-selection 정확도(95.6%)와는 별개로, 이 tool은
프로덕션 관점에서 동시성 처리 방식을 반드시 점검해야 합니다.

### 3-3. [Major] `search_previous_conversations` ↔ Week4 `search_conversation_messages` 혼선 (31%)

`search_previous_conversations` 실패 28건 전부가 Week4의
`search_conversation_messages`(앱 내부 채팅 기록 RAG) 호출로 새어나갔습니다.
예:

```
"철수랑 나눈 대화에서 API 연동 실습 관련된 거 찾아줘"
  -> search_conversation_messages 호출 (기대: search_previous_conversations)
  -> 답변: "...검색 결과에 명확히 나타나지 않았습니다"
```

두 tool은 이름과 목적이 상당히 비슷합니다 — 하나는 "외부 멤버의 과거 대화"
(Week5, MCP 서버), 하나는 "이 앱에서 나눈 채팅 기록"(Week4, ChromaDB). 사람
이름이 등장하는 질문에서도 LLM이 30% 정도는 Week4 tool로 잘못 흘러가며,
그 경우 실제 외부 대화 데이터를 전혀 못 찾고 "없다"고 답합니다 — **정보가
있는데 없다고 답하는 조용한 실패**라서 사용자가 알아채기 어렵습니다.

### 3-4. [Moderate] `load_conversation_messages` 단독 호출 잘 안 됨 (50%)

conversation_id를 프롬프트에 직접 명시했는데도, 실패 30건 중 25건은
`search_previous_conversations`만 호출하고 끝났습니다(정작 메시지 전체를
불러오는 `load_conversation_messages`는 안 부름). 나머지 5건은 Week4
`search_conversation_messages`로 샘. 이 결과는 프롬프트 설계 자체의 한계도
있습니다 — 실제 사용자는 대화 ID를 미리 알기 어려우므로, 이 테스트는
"이미 ID를 알고 있다"는 부자연스러운 상황을 가정합니다. 다만 그런 상황에서도
"이미 있는 ID로 전체 메시지를 가져오라"는 명시적 요청조차 절반은
`search_previous_conversations` 재검색으로 대체된다는 건, 이 tool의 사용
시점이 프롬프트에 충분히 명확하지 않다는 신호입니다.

## 4. 정상 동작 확인된 부분

- **`list_shared_schedules` 97.5%, `collect_member_schedules` 95.6%** —
  Week5의 두 핵심 "메인과제" tool(가이드가 "Week6 하위 agent가 그대로
  재사용"한다고 명시한 tool들)은 실제로 높은 정확도로 선택됩니다.
- **control false positive 0/90** — 내 일정·잡담·다른 주차 기능 요청에서
  Week5 외부 tool이 잘못 불린 적이 없습니다.
- **예외/크래시 0/500** — MCP subprocess 호출 500회(+`collect_member_schedules`
  내부의 추가 MCP 호출) 동안 처리되지 않은 예외가 없었습니다. 3-2절의 지연은
  "느림"이지 "깨짐"은 아니었습니다.
- 기존 `checks/week05_golden.py`(40케이스, 이분법 판정)의 `external_people
  83.3%` / `control 오호출 0` 결과와 방향은 일치합니다 — 다만 이번처럼 tool을
  세분화하니 그 83.3% 안에 "정답 tool이 아닌 다른 Week5 tool로 우연히 통과한"
  케이스(`extract_schedules_from_history` 자리를 `collect_member_schedules`가
  대신한 것)가 섞여 있었다는 게 새로 드러났습니다.

## 5. 정량 비교 — 기존 40케이스 golden vs 이번 500케이스

| | `checks/week05_golden.py` (40케이스, 이분법) | 이번 500케이스 (tool별 세분화) |
| --- | --- | --- |
| 판정 방식 | "Week5 tool 중 하나라도 호출" | tool 이름까지 정확히 일치해야 pass |
| 외부 멤버 관련 pass율 | 83.3% (20/24) | 카테고리별로 0%~97.5%까지 편차 큼 |
| control 오호출 | 0/16 | 0/90 |

이분법 판정에서는 "정답과 다른 Week5 tool이 불려도 통과"로 처리되기 때문에,
`extract_schedules_from_history`가 사실상 죽어 있는 tool이라는 것과
`collect_member_schedules`의 동시성 지연 문제 둘 다 40케이스 golden에서는
드러나지 않았습니다. tool 단위로 쪼개서 봐야만 잡히는 문제였습니다.

## 6. 데이터 무결성

`data/chroma`, `data/kanana_app.sqlite3`, `data/kanana_external_people.sqlite3`의
임시 복사본에 대해서만 실행했고, 실제 `data/`는 건드리지 않았습니다. 실행
전후로 row 개수를 대조했습니다:

| 테이블 | 실행 전 | 실행 후 |
| --- | --- | --- |
| `kanana_app.sqlite3::structured_requests` | 5 | 5 |
| `kanana_app.sqlite3::schedules` | 3 | 3 |
| `kanana_app.sqlite3::todos` | 1 | 1 |
| `kanana_app.sqlite3::reminders` | 1 | 1 |
| `kanana_external_people.sqlite3::external_conversations` | 6 | 6 |
| `kanana_external_people.sqlite3::external_messages` | 6 | 6 |
| `kanana_external_people.sqlite3::external_schedules` | 21 | 21 |

임시 복사본(더미 데이터)은 분석 후 삭제했고, 케이스별 원본 trace(`results_500_w5.jsonl`)는
스크래치 디렉터리에 보존해뒀습니다.

## 7. 재현 방법

케이스 생성/실행 스크립트(`gen_cases_w5.py`, `run_cases_w5.py`, `analyze_w5.py`)는
이번 실행 전용 스크래치 코드로 저장소에는 포함하지 않았습니다. Week4와 같은
방법론(1절)으로 재작성해 재현할 수 있으며, `run_active_week_agent(5, [...])`를
호출하는 부분만 다릅니다. `collect_member_schedules`의 동시성 지연(3-2절)을
재현/진단하려면 이 tool만 동시 호출 수를 늘려 반복 실행하는 별도 스트레스
테스트가 필요합니다.
