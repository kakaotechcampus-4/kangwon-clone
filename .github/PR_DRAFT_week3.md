## 과제 목표
이번 주차 과제를 통해 무엇을 배우고자 했는지 간단히 적어요.

- Week 2에서 구조화한 일정/할 일/알림 요청을 SQLite에 영구 저장하기
- 저장된 요청/일정을 다시 조회해서 새 대화에서도 기억이 유지되도록 만들기
- LangChain `@tool(args_schema=...)`로 입력을 검증한 뒤, 검증된 값을 그대로 저장 계층(`AppSQLiteStore`)에 넘기는 얇은 tool 본문 작성 연습

---

## 과제 위치
- 작업 브랜치 : `kimeunwoo/week3` → 본인 통합 브랜치 `kimeunwoo/final` 로 PR
- 주요 파일 : `student_parts/week03_build_nanas_logbook.py`

> 제공 코드(`fixed/` 등)는 수정하지 않고, `student_parts/` 의 **본인 주차 파일**을 구현해요.
> 리뷰어(담당 멘토)는 PR 을 열면 **자동 지정**되니 직접 추가하지 않아도 돼요.

---

## 과제 범위
이번 PR 에서 어디까지 했는지 체크해요. (해당하는 곳에 모두)

- [x] 메인 과제 완료
- [ ] 심화 과제까지 완료

---

## 구현한 기능
이번 주차 **메인 과제** 중 구현한 항목에 체크해요.

- [x] save_structured_request
- [x] list_saved_requests / get_saved_request
- [x] personal_list_saved_schedules

---

## 심화 과제
**심화 과제**를 시도했다면 체크하고 무엇을 했는지 간단히 적어요.

- [ ] 미션명 : (이번 PR에서는 시도하지 않음)

---

## AI 활용 내역
AI를 활용해 구현하거나 수정한 내용을 기록해요.
어떤 프롬프트를 썼는지보다 **어떤 결과를 받았고 어떻게 직접 수정했는지**를 중심으로 작성해요.

### save_structured_request / list_saved_requests / get_saved_request / personal_list_saved_schedules 구현
- AI 활용 내용 :
`fixed/app_store.py`의 `AppSQLiteStore` 메서드 시그니처와 `student_parts/week01_wake_up_nana.py`·`week02_structure_natural_language_requests.py`의 기존 패턴(`_store()`, `json_payload()`, `tool_result()` 헬퍼 사용법, `@tool(args_schema=...)` 구조)을 근거로 4개 메인과제 tool의 뼈대를 받았어요. `save_structured_request`는 함수 인자를 dict로 모아 `None` 값을 제외한 뒤 `store.save_structured_request(payload)`에 넘기고, 나머지 3개는 각각 `list_saved_requests`/`get_saved_request`/`list_schedules` store 메서드에 필터를 그대로 전달하는 형태예요.
- 직접 수정한 부분 :
(여기에 본인이 실제로 바꾼 부분을 적어주세요 — 예: 변수명, 필드 우선순위, 예외 케이스 등)
- 수정 이유 :
(여기에 이유를 적어주세요)

### 기능명
- AI 활용 내용 :
- 직접 수정한 부분 :
- 수정 이유 :

---

## 구현하면서 고민한 점
막혔던 부분, 고민한 내용, 해결 방법을 자유롭게 적어요.

- 고민한 점 : `personal_list_saved_schedules`의 기본 `kind`를 `None`으로 둘지 `"personal_schedule"`로 고정할지, 그리고 저장 시 `None` 필드를 제외해야 하는 이유(신뢰할 값만 `raw_json`/컬럼에 남기기 위함) 등을 정리하는 과정
- 해결 방법 : `AppSQLiteStore`의 각 메서드가 `payload.get(key, default)` 방식으로 값을 읽는다는 걸 확인하고, tool 쪽에서는 얇게 필터링만 하고 실제 기본값 처리는 store에 맡기는 방향으로 정리함

---

## 과제 회고 (KPT)
과제를 마치고 KPT 회고를 적어요.

- **Keep** (좋았고 계속 유지할 점) : tool 본문을 얇게 유지하고 검증(Pydantic args_schema)과 저장 로직(AppSQLiteStore)의 책임을 분리한 것
- **Problem** (아쉬웠거나 막혔던 점) : (본인 경험을 적어주세요)
- **Try** (다음에 시도해볼 점) : 심화 과제(수정/삭제, Week 1 호환 생성)까지 이어서 구현해보기
