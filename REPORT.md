# Week 1 과제 보고서 — Choe Yongbin

## 과제를 시작하기 전에

코드를 바로 작성하기보다 전체 구조를 먼저 읽고 이해하는 데 시간을 쏟았습니다.  
모르는 단어가 나오면 검색하고, 그 단어와 연관된 개념도 함께 찾아보다 보니 생각보다 시간이 많이 걸렸습니다.

AI를 참고했지만 되도록 직접 타이핑해서 작성하려고 노력했습니다.  
VS Code 자동완성이 계속 방해했지만… 달콤했습니다.

---

## 구현 내용

`student_parts/week01_wake_up_nana.py` 안의 개인 일정 CRUD tool 3개를 구현했습니다.

### personal_create_schedule

- `title`, `date`, `start_time`, `end_time`, `attendees` 인자로 일정 dict를 생성합니다.
- `id`는 `_new_personal_id()`, `created_at`은 `_now_iso()`로 채웁니다.
- `session_id = current_session_scope()`를 호출해 현재 대화 범위를 dict에 포함시키고 `PERSONAL_SCHEDULES`에 append합니다.
- 반환 JSON: `ok`, `tool_name`, `created_schedule`

### personal_list_schedules

- `_current_session_schedules()`로 현재 대화 범위의 일정만 먼저 걸러냅니다.
- `date_from`, `date_to`가 있으면 YYYY-MM-DD 문자열 비교로 날짜 범위 필터를 적용합니다.
- 리스트 원본(`PERSONAL_SCHEDULES`)은 수정하지 않습니다.
- 반환 JSON: `ok`, `tool_name`, `schedules`

### personal_delete_schedule

- `session_id = current_session_scope()`로 현재 범위를 확정합니다.
- 현재 범위이면서 `schedule_id`가 일치하는 항목만 제외한 리스트를 `PERSONAL_SCHEDULES[:]`에 대입해 객체 참조를 유지합니다.
- 삭제 전후 길이 차이로 `deleted` 값을 만듭니다.
- 반환 JSON: `ok`, `tool_name`, `deleted`

---

## 실행 방법

```powershell
cd kakao_kangwon_week1\kangwon-clone
uv run python app.py
```

브라우저에서 `http://127.0.0.1:7860` 접속 후 채팅 탭에서 일정 생성·조회·삭제를 테스트합니다.  
상세 탭의 trace에서 LLM이 어떤 tool을 골랐는지와 반환 JSON을 확인합니다.

---

## 구현하면서 마주친 문제

**session_id 누락 버그**  
`personal_create_schedule`에서 `session_id = current_session_scope()` 호출을 빠뜨려 `NameError`가 발생했습니다.  
`personal_delete_schedule`과 `_current_session_schedules()`의 패턴을 참고해 동일하게 수정했습니다.

**system prompt 언어**  
`CHAT_MEMORY_PROMPT`를 영어로 작성했는데, LLM이 instruction 언어를 출력 언어의 단서로 쓸 수 있어 영어 입력 시 영어 응답이 나올 가능성이 있다는 점을 나중에 알았습니다.

**응답 속도**  
단순 인사에도 약 8초가 걸렸는데, LangChain agent가 tool 사용 여부를 판단하는 LLM 호출과 최종 응답 생성 호출을 최소 2회 수행하고, 외부 프록시를 경유하기 때문이었습니다. 코드 버그가 아닌 구조적인 비용임을 파악했습니다.

---

## 알게 된 것

- LangChain `@tool`은 문자열 반환이 가장 안정적이고, dict는 `_json()`으로 감싸야 합니다.
- `PERSONAL_SCHEDULES[:]`에 대입하면 리스트 객체 자체를 유지하면서 내용만 교체할 수 있습니다.
- `current_session_scope()`로 대화별 격리를 구현하면 다른 대화의 일정을 잘못 건드리는 문제를 방지할 수 있습니다.
- 코드를 먼저 읽고 이해한 뒤 구현하면 왜 그렇게 짜야 하는지가 명확해집니다.
