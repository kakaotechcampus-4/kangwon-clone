# Week 6 구현 PRD 체크리스트

`student_parts/week06_kanamate_decides_schedule.py` supervisor 구조 구현. 이 문서는 **무엇을·어떤 순서로·어떻게 통과 확인**하는지의 체크리스트. 세부 설명은 `WEEK06_IMPLEMENTATION_GUIDE.md`, 테스트는 `WEEK06_TEST_CASES_2200.md`.

## 1. 목표 / 범위
- **목표**: 한 agent가 다 하던 구조를 supervisor + Nana/Kana 하위 agent로 분리. supervisor는 `nana_agent`/`kana_agent`만 보고 위임.
- **In scope**: `student_parts/week06_*.py`의 11개 스텁, `checks/week06_*`.
- **Out of scope**: `fixed/`·이전 주차 파일 수정 금지. `propose_group_schedule`(호환용, 완성됨) 손대지 않음.

## 2. 성공 기준 (Acceptance Gate)
- [ ] `checks/week06_deterministic.py` **624/624 pass** (static 24 + property 600) — 하드 게이트
- [ ] `import student_parts.week06_kanamate_decides_schedule` 예외 없음
- [ ] `./run.sh --week6` 정상 기동
- [ ] golden(배치): 라우팅 정확도(개인→nana / 그룹→kana) 목표치 설정 후 측정, control 오호출 0
- [ ] 변경 파일이 `student_parts/week06_*` + `checks/`뿐 (git diff 확인 — 멘토 2-6)
- [ ] 테스트 파일은 수정하지 않고 코드로 통과 (멘토 2-3)

## 3. 구현 체크리스트

### Phase A — 메인: 프롬프트 4종 (동작의 8할)
- [ ] **`week06_prompt_parts`**: `[*week05_prompt_parts(), <supervisor 위임 지시>]`
  - [ ] supervisor는 직접 처리 X, `nana_agent`/`kana_agent`로만 위임 명시
  - [ ] 라우팅 기준(개인 일정/저장/RAG→Nana, 외부멤버/공유/공통시간→Kana)
  - [ ] 게이트: static(nonempty·accumulate week05·nana_agent/kana_agent 언급)
- [ ] **`nana_prompt_parts`**: `[*week04_prompt_parts(), <Nana 역할>]`
  - [ ] 개인 일정/저장/RAG 담당, 그룹 조율은 "담당 아님" 짧게
- [ ] **`kana_prompt_parts`**: **빈 `[]`에서 시작** (누적 없음 — 빼먹기 쉬움)
  - [ ] Kana 역할(외부멤버 대화/일정, 공유 일정, 공통 시간·최종 결정) 처음부터 작성
  - [ ] 확정 일정 저장은 Nana 담당이라고 답하게
  - [ ] (추가과제 시) find_common_available_slots→decide_final_slot 이어서 호출 지시
  - [ ] 게이트: static(nonempty·Kana·kana tool 이름 언급)
- [ ] **`supervisor_system_prompt`** TODO: 누적 뒤 "반드시 nana/kana 중 하나 호출 후 그 결과만 근거로 답"

### Phase B — 메인: 위임 wrapper 2개
- [ ] **`nana_agent(query)`**: `_NANA_SUBAGENT` 없으면 `create_agent(chat_model(), week04_tools(), nana_system_prompt())`로 1회 생성·재사용
  - [ ] invoke 후 `extract_agent_events`·`extract_final_text`로 trace/answer
  - [ ] 반환 JSON: `answer`, `trace`, `inner_tool_names` (+ selected_agent)
- [ ] **`kana_agent(query)`**: `_KANA_SUBAGENT`를 `kana_tools()`+`kana_system_prompt()`로 1회 생성·재사용
  - [ ] 하위 trace content 훑어 `final_slot_payload`(final_slot 든 dict)·`final_decision_payload` 끌어올림
  - [ ] 반환 JSON: `answer`, `trace`, `inner_tool_names`, `final_slot_payload`, `final_decision_payload`

### Phase C — 추가: tool description 2개 (= 계약, 채우면 slot tool 판단 근거)
- [ ] **`FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION`**
  - [ ] "이 tool은 후보를 계산하지 않는다. agent가 busy_rows 보고 candidate_slots 직접 채워라"
  - [ ] 후보 형식(date YYYY-MM-DD, start/end HH:MM, duration_minutes, reason), busy와 겹치면 안 됨, busy_rows 복사
  - [ ] 끝내지 말고 decide_final_slot 이어서 호출 유도
  - [ ] 게이트: static(candidate_slots·busy_rows·YYYY-MM-DD·HH:MM·decide_final_slot 포함)
- [ ] **`DECIDE_FINAL_SLOT_DESCRIPTION`**
  - [ ] "자동 선택 X. selected_index/selected_slot·final_slot을 agent가 직접"
  - [ ] final_slot 형식 'YYYY-MM-DD HH:MM-HH:MM', 미확정이면 null·needs_agent_selection=true
  - [ ] 게이트: static(final_slot·needs_agent_selection·selected_index 포함)

### Phase D — 추가: slot/결정 함수 3개
- [ ] **`find_common_available_slots_dict`**
  - [ ] `normalize_external_member_names` + members에 **"나" 포함**
  - [ ] `normalize_date_bound`로 날짜 정규화
  - [ ] `busy_rows` None이면 `collect_member_schedules.invoke({...})`로 수집
  - [ ] `find_common_available_slots_payload(...)`에 전달
- [ ] **`find_common_available_slots`** (tool): `_dict` 결과를 `json_payload`/`json.dumps`로 반환
- [ ] **`decide_final_slot`** (tool): 인자 그대로 `decide_final_slot_payload(...)`에 전달(직접 선택 X), JSON 반환
  - [ ] 게이트: property 600 (9·10·11)

### Phase E — 조립/정리
- [ ] 추가과제 **안 할 경우**: `kana_tools()`에서 `find_common_available_slots`·`decide_final_slot` 제거 **+ Kana 프롬프트에서도 언급 삭제**
- [ ] (선택) `checks/tool_inventory.py`에 week6 대응(단 supervisor는 2 tool만 노출 — 인벤토리 규칙은 하위 agent 기준으로)

## 4. 마일스톤(권장 순서)
1. Phase A → B → `./run.sh --week6`로 **위임 기본 흐름** 확인(개인→nana, 그룹→kana)
2. Phase C → D → property 600 통과 → **그룹 조율 흐름** 확인
3. golden 배치로 라우팅·행동 측정 → 실패 케이스 눈으로(멘토 2-5)

## 5. 리스크 / 함정 체크
- [ ] `kana_prompt_parts` 빈 채로 두지 않기 (역할 백지)
- [ ] 하위 agent는 supervisor 프롬프트 못 봄 → 역할은 각 프롬프트에
- [ ] supervisor 프롬프트에서 실무 tool 이름 부르라고 쓰지 않기 (2 tool만 봄)
- [ ] description 비면 agent가 빈 인자로 부름 → 형식·"계산 안 함" 명시
- [ ] `decide_final_slot`에서 Python이 최종 시간 직접 고르지 않기 (pass-through)
- [ ] 같은 에러 2회 반복 시 멈추고 기록(멘토 2-1)

## 6. 검증 게이트 (커밋 전)
- [ ] `checks/week06_deterministic.py` 624/624
- [ ] import OK / `./run.sh --week6` 기동
- [ ] `git diff --name-only`가 `student_parts/week06_*`·`checks/`·`6week_docs/`뿐
- [ ] (golden) 라우팅 목표치·control 0 확인 후 PR
