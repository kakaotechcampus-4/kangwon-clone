# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A student clone of the "Kanana Schedule Agent" course project (카카오테크 캠퍼스). Each week adds one LangChain agent module under `student_parts/`. The `main` branch tracks Week 1-4; the full Week 1-6 curriculum lives on the `week_1_to_6f` branch (not present here). See `README.md`, `PROJECT_OVERVIEW.md`, and `CURRICULUM.md` for the course-facing docs (currently Week-1-only in wording, but the same "read the guide comment, implement the TODOs, verify via trace" pattern applies to every week's file).

## Commands

```bash
./run.sh --install     # uv sync, then run the Week 1 app
./run.sh                # run app.py with KANANA_ACTIVE_WEEK=1
./run.sh --week1        # ... --week4   run app.py with that week's agent active
./run.sh --conda --install / --conda   # legacy conda fallback via environment.yml
```

- Package manager is `uv`; `pyproject.toml` + `uv.lock` are authoritative. `requirements.txt` / `environment.yml` are fallback only.
- `uv add "pkg>=1.0"`, `uv remove pkg`, `uv lock` for dependency changes.
- Python pinned to 3.11 (`.python-version`, `requires-python = ">=3.11,<3.12"`).
- **No automated test harness exists in this repo** (explicitly stated in README). Verification is manual: run the app, chat with it, and read the "상세" (detail) tab's trace JSON to confirm which tool fired and what payload it returned.
- `.env` (copy from `.env.example`) needs `PROXY_TOKEN` or the agent won't run — without it, `run_active_week_agent` returns a canned "please add a key" response instead of invoking LangChain.

## Architecture

**Request flow:** `app.py` (Gradio UI) → `fixed/agent_runtime.py::AgentRuntime` (persists chat messages, wraps stream) → `fixed/week_agent_registry.py::run_active_week_agent`/`stream_active_week_agent` → dynamically imports `student_parts.week0N_*` by `KANANA_ACTIVE_WEEK` and calls its `build_week_agent()` → LangChain agent executes, tool calls/results become the trace JSON shown in the UI's "상세" tab.

**`fixed/` vs `student_parts/`:** `fixed/` is instructor-owned infrastructure (config, DB stores, LLM client, trace extraction, MCP client) — treat as read-only reference unless a task explicitly asks to change it. `student_parts/week0N_*.py` is where all student implementation happens; each file starts with a Korean `[N주차 수강생 구현 가이드]` comment block naming exactly which functions are in-scope for 메인과제 (main assignment) vs 추가과제 (bonus assignment) — read that block before touching a week's file, it is the actual spec.

**Per-week module contract:** every `week0N_*.py` exposes the same three entry points, which is how `week_agent_registry.py` treats them interchangeably:
- `weekNN_tools()` — the LangChain tool list for that week, usually built by taking the *previous* week's tool list and swapping/appending tools (e.g. `week03_tools()` starts from `week01_tools()` and replaces `personal_create_schedule`, then appends Week 2/3 tools). A tool "disappearing" or reverting to a stub in a later week's assembly function is a real regression class here — check the accumulation logic, not just the individual tool body.
- `weekNN_prompt_parts()` — list of system-prompt string fragments, accumulated from the previous week via `weekNN_prompt_parts() = [*week(N-1)_prompt_parts(), ...new fragments]`. Order matters: `join_system_prompt()` tells the LLM that later fragments take precedence when instructions conflict.
- `build_week_agent()` — builds (and caches in a module-level `_WEEKNN_AGENT` global) the `create_agent(...)` instance from `chat_model()` + `weekNN_tools()` + `weekNN_prompt_parts()`.

**Data layer (`fixed/`):**
- `fixed/config.py` — single `CONFIG` singleton read once from `.env` at import time; every other module reads paths/model names from `CONFIG`, never recomputes them.
- `fixed/app_store.py::AppSQLiteStore` — one SQLite file (`data/kanana_app.sqlite3`) holding both Gradio chat history (`conversations`/`messages`) and Week 3+ structured data (`structured_requests`, `schedules`, `todos`, `reminders`). Personal/group schedules are additionally mirrored to an external "shared" store via `fixed/external_mcp.py` on save/update/delete — DB writes and external sync are intentionally not in the same transaction (external failure shouldn't roll back the local save).
- `fixed/reference_store.py` / `fixed/conversation_rag_store.py` — Week 4 ChromaDB-backed stores (personal reference notes, and lazy-synced chat message embeddings) under `data/chroma`.
- `fixed/session_scope.py` — current conversation/session scoping used to keep "this conversation" separate from historical search results.
- `fixed/llm.py::chat_model()` — the one place a `ChatOpenAI` client is constructed (against the course proxy, not OpenAI directly); raises if `PROXY_TOKEN` is missing.
- `fixed/langchain_trace.py` — turns a LangChain agent result/stream chunks into the trace dict / status strings the UI displays; per-week modules may override `extract_langchain_trace` and the registry falls back to the common one if absent.

**Tool implementation pattern (all weeks):** tools are `@tool` or `@tool(args_schema=SomePydanticModel)` functions that return a JSON string (`json.dumps(..., ensure_ascii=False)`, wrapped via a `json_payload`/`tool_result` helper for Korean-safe encoding). When `args_schema` is set, LangChain validates the LLM's arguments against that Pydantic model *before* the function body runs — so defensive `if x is None` handling inside the function body for a field that schema already defaults/requires is dead code in the normal call path (only matters if something calls the underlying function directly, bypassing tool invocation).

**`student_parts_baseline/`** holds instructor reference solutions for *previous* weeks (added by the `KTC_WEEKLY_SYNC.md` sync flow, see below) — reference only, never copy it over the student's own `student_parts/` files.

## Git workflow for this repo

Branch shape per student: `<name>/final` accumulates all merged week work across the course; `<name>/weekN` branches off the latest `<name>/final`, and its PR is opened with `base=<name>/final`. `main` is the instructor's branch, containing only Week 1-4 material.

`KTC_WEEKLY_SYNC.md` (in repo root) is the exact, reusable procedure for merging new lecture material from `main` into `<name>/final` without losing student code — it defines the diagnose → merge → verify → finish shell blocks and the conflict-resolution rule (`student_parts/**` always keeps the student's version; `fixed/**`/`run.sh` take the instructor's version unless the student directly edited them, in which case ask). Follow it verbatim, in order, when asked to sync/update lecture material — do not improvise a different merge strategy. Never `git rebase`, `git push --force`, or `git reset --hard` in this repo; a prior incident wiped merged PR history that way.
