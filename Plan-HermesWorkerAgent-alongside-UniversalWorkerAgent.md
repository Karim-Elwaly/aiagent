## Plan: HermesWorkerAgent alongside UniversalWorkerAgent

This adds a second worker, `HermesWorkerAgent`, that the existing activity can use in place of `UniversalWorkerAgent` with no other changes. It calls tools through the Hermes function-calling protocol: native OpenAI `tool_calls` when the server supports them, and `<tool_call>`/`<tool_response>` tags when it doesn't. Research turned up something useful: most of the protocol layer is already in the repo but nothing in production uses it. [tool_call_parser.py](src/core/tool_call_parser.py) already has a parser for native calls, Hermes tags, JSON and ReAct formats, plus argument coercion, "did you mean" suggestions, and OpenAI/Hermes-XML schema formatters. [messages.py](src/core/messages.py) has `ParsedToolCall`, `ToolResult`, `ToolCallRecord` and a v2 checkpoint schema. `Settings.tool_call_mode` exists but nothing reads it. The new worker uses all of these instead of a sixth parser. The Nous hermes-agent features come later, as a separate Phase E.

**Phase A: Foundations** (A1–A3 can run in parallel)
1. **A1. LLM client.** Add `chat_with_tools(messages, tools_schema)` to `LocalLLMClient` in [llm_client.py](src/core/llm_client.py). It sends a non-streaming POST with `tools` and `tool_choice: "auto"` and returns a small `LLMTurn` (content, raw `tool_calls`, finish_reason). It reuses the retry/backoff loop and `_is_retryable_error`, and its messages are typed `list[dict[str, Any]]` so assistant `tool_calls` and `role: "tool"` messages fit. `chat`, `_chat_once` and `chat_stream` stay unchanged.
2. **A2. Transport resolver.** Add a small function in the new worker module that turns `Settings.tool_call_mode` into `native` or `tags`. `auto` and `legacy` both mean auto for this worker. In auto mode it starts native and switches to tags if:
   - the server returns HTTP 400/422 on the `tools` parameter, or
   - the model writes `<tool_call>` text instead of native calls.

   The result is cached per `(base_url, model)` in module memory.
3. **A3. Persona protocol.** Add `protocol: str = "legacy"` to `PersonaSynthesizer.synthesize` and `synthesize_from_profile` in [synthesizer.py](src/persona/synthesizer.py).
   - `legacy` produces exactly today's output, so existing tests stay valid.
   - `hermes` replaces the `{"tool": ...}` examples from `_format_tools` and the forced `FINAL_ANSWER:` rules with a short Hermes block: call tools via the tool interface, and a turn with no tool calls is the final answer.
   - In tags mode the worker adds `format_tools_to_hermes_xml(tools)` itself. Profile templates such as the SOC investigator's still get their domain text, but the protocol section is swapped.

**Phase B: Worker** (*depends on A*)
Plan: HermesWorkerAgent alongside UniversalWorkerAgent

4. New [src/workers/hermes_worker.py](src/workers/hermes_worker.py). It has the same `__init__(llm, max_iterations, max_output_chars)` and `execute(...)` signatures and returns `TaskResult` like `UniversalWorkerAgent`. The loop:
   - **Model call.** Native mode uses `chat_with_tools`. Tags mode uses `chat_stream` (feeding `on_token`) and falls back to `chat`.
   - **Parsing.** Every response goes through `parse_tool_calls(content, native_tool_calls)`.
   - **Running calls.** All calls in a turn run sequentially, in order.
     - An unknown tool name returns an error result that includes the `suggest_closest_tool` hint.
     - Arguments go through `coerce_and_validate_args`.
     - Each call runs via `ToolSpec.invoke` under the task timeout, and output passes through `smart_truncate` from `src/core/text_utils`.
     - `on_event` sends `tool_start`/`tool_end` with the same shapes as today.
   - **Results back to the model.** Native mode appends an assistant message carrying `tool_calls`, then one `role: "tool"` message per call with its `tool_call_id`. Tags mode appends the assistant text, then a `user` message with `<tool_response>{"name","content"}</tool_response>` blocks.
5. Guardrails kept the same as the existing worker:
   - **Grounding:** if tools exist and none has run, it sends up to 2 steering nudges, then returns FAILED with the same "No evidence collected" message.
   - **Max iterations:** returns COMPLETED with the `[Reached max N iterations]` prefix plus the accumulated tool outputs.
   - **Timeouts:** raises `TransientLLMError` on timeout, as the existing worker does.
   - **Final answer:** strips `FINAL_ANSWER:`/`CANNOT_COMPLETE:` prefixes if present and mirrors `_extract_final_answer` semantics.
6. **Checkpoints.** The heartbeat payload is v2: `schema_version: 2`, `engine: "hermes"`, `transport`, `task_id`, `step`, `messages`, `tool_calls_made`, `tool_history` (as `ToolCallRecord` dicts). On resume it only accepts checkpoints where `engine == "hermes"` and starts fresh otherwise. This prevents a crash when a Temporal retry happens after the engine setting changed.
7. **Context budget.** When the conversation goes over `settings.worker_max_context_chars`, the most recent N tool results stay intact and older ones are reduced to head/tail via `smart_truncate`. Native `tool_call_id` pairing is never broken.

**Phase C: Engine selection** (*depends on B; can overlap with D*)

8. Add `Settings.worker_engine: str = "universal"` in [config.py](src/core/config.py).
9. Add `worker_engine: str | None = None` to `AgentProfile`, `AgentCreateRequest` and `AgentUpdateRequest` in [agent_models.py](src/core/agent_models.py). `None` means inherit the global setting. Copy the field in the create/update endpoints in [main.py](src/api/main.py) (~L1572, ~L1603). On update, `""` maps to `None` so a user can reset to inherit. Existing agent JSON files still load because the field is optional.
10. New [src/workers/factory.py](src/workers/factory.py):
    - `resolve_engine(profile, settings)`: per-agent value, then global value, then `"universal"`. Unknown values log a warning and fall back to universal.
    - `create_worker(engine, llm, settings)`.
11. [activities.py](src/orchestrator/activities.py) `execute_task` (~L264–L290) resolves the engine before persona synthesis, passes `protocol` to the synthesizer, builds the worker through the factory, logs the engine, and emits a `worker_engine` event on the bus. The direct engine in main.py and the Temporal path both go through `execute_task`, so nothing else changes. [tests/eval/runner.py](tests/eval/runner.py) gets an optional engine argument.

**Phase D: UI** (*parallel with C once step 9's field names are fixed*)

12. Add optional `worker_engine` to `LLMConfigPayload` (main.py L178). `GET /api/settings/llm` returns it. `POST` saves it via `save_runtime_settings` only when it's present and in `{"universal","hermes"}`, otherwise returns 422.
13. In [index.html](src/ui/index.html), add a select `llm-input-worker-engine` in the LLM panel near L516 with options Universal ReAct and Hermes function-calling. In [app.js](src/ui/js/app.js), load it in `loadCurrentLlmSettings` (~L2282) and send it from the save handler (~L2444).
14. Add a select `agent-form-worker-engine` to the agent form near L995 (Inherit global / Universal / Hermes). Fill it in `loadAgentIntoForm` (~L3191) and include it in the payload (~L3279). Copy the `mcp-transport` static select pattern.

**Phase E: Hermes-agent features** (later, its own plan once A–D are measured)

15. **Skills as context.** Replace the fake echo-tools from `default_skill_executor` with `skills_list`/`skill_view(name)` for the Hermes engine, so skill text reaches the model as guidance instead of a fake "Status: Success".
16. **Real delegation.** Replace the simulated `delegate_task` with a nested `HermesWorkerAgent`: isolated context, restricted toolset, depth limit of 1.
17. **Memory and todos.** Inject memory recall when `enable_memory` is on, and scope `todo_tracker` per task.

**Relevant files**
- [src/core/llm_client.py](src/core/llm_client.py): add `chat_with_tools`, `LLMTurn`
- [src/core/tool_call_parser.py](src/core/tool_call_parser.py): reuse `parse_tool_calls`, `coerce_and_validate_args`, `suggest_closest_tool`, `format_tools_to_openai_schema`, `format_tools_to_hermes_xml`
- [src/core/messages.py](src/core/messages.py): reuse `ParsedToolCall`, `ToolResult`, `ToolCallRecord`, checkpoint v2
- [src/persona/synthesizer.py](src/persona/synthesizer.py): `protocol` parameter
- [src/workers/hermes_worker.py](src/workers/hermes_worker.py) (new), [src/workers/factory.py](src/workers/factory.py) (new)
- [src/workers/universal_worker.py](src/workers/universal_worker.py): reference only for guardrail semantics; **no changes**
- [src/orchestrator/activities.py](src/orchestrator/activities.py): factory seam at ~L284
- [src/core/config.py](src/core/config.py), [src/core/agent_models.py](src/core/agent_models.py), [src/api/main.py](src/api/main.py), [src/ui/index.html](src/ui/index.html), [src/ui/js/app.js](src/ui/js/app.js)
- [tests/eval/runner.py](tests/eval/runner.py): optional engine argument

**Verification**
1. New `tests/unit/test_hermes_worker.py`, using a fake LLM in the style of [test_react_loop.py](tests/unit/test_react_loop.py):
   - native tool_calls path and tags path
   - two calls in one turn run in order
   - hallucinated tool returns a suggestion
   - string-to-int argument coercion
   - grounding failure
   - max-iterations prefix
   - heartbeat v2 shape, resume from a hermes checkpoint, universal checkpoint ignored
   - switch from native to tags on HTTP 400 and on `<tool_call>` text
   - `on_event` and `on_token` emission
2. `tests/unit/test_worker_factory.py`: per-agent override beats global beats default; invalid value falls back to universal; legacy agent JSON without the field still loads.
3. Persona tests: `protocol="legacy"` output is byte-identical to today's; `protocol="hermes"` has no `{"tool":` instruction.
4. LLM client test: monkeypatch `httpx.AsyncClient.post`, assert the payload includes `tools`/`tool_choice` and the reply is parsed into `LLMTurn`.
5. Add `hermes_worker.py` to `GUARDED_PATHS` in [test_soc_benchmark_leakage.py](tests/unit/test_soc_benchmark_leakage.py).
6. Full suite: `.\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/integration` must show the same 24 pre-existing failures with all new tests passing. compileall must be clean.
7. Manual A/B: LM Studio with `gpt-oss-20b`, SOC case 1 and case 5 through the 6-phase template, `worker_engine=hermes` vs `universal`. Compare tool calls made, iterations, grounding failures and report content. Then flip the UI selects and confirm the setting is saved to `runtime_settings.json` and the agent JSON.

**Decisions**
- Default stays `universal`, so nothing changes until someone opts in.
- I'm reusing `tool_call_mode` instead of adding a new flag, because it was added for exactly this. The universal worker keeps ignoring it.
- The universal worker isn't modified at all. Both workers share only the tools, the persona and the checkpoint transport.
- Excluded from this plan: Phase E features, streaming for native tool calls (native mode is non-streaming, so `on_token` only fires in tags mode), and concurrent tool execution.

**Further considerations**
1. **Streaming in native mode.** Without it, the live token view stays blank while a native call runs. I recommend accepting that for now and adding SSE `tool_calls` delta assembly later if the A/B shows Hermes is worth keeping.
2. **Choosing a model.** `gpt-oss-20b` in LM Studio supports native tools. A Nous Hermes model would exercise the tags path. If you want a real test of the fallback, pick one Hermes-family model for the A/B as well.
