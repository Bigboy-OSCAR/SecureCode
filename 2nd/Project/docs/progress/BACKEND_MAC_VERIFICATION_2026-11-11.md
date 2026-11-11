# Mac backend verification — 2026-11-11

This review applies the user's current local-only Mac scope. The latest user instruction authorizes commits and pushes and supersedes the roadmap's earlier team-only Git restriction.

## Existing implementation audit

The installed Python environment lacked the locked `pypdf` dependency, preventing service startup. `uv sync --locked` installed the declared dependency. The original Python suite passed 495 tests with one opt-in live test skipped. Host checks initially failed only because local listeners were disallowed in the restricted execution environment; they were rerun with local networking enabled. A UI Ajv installation mismatch was handed to the UI owner.

## Implemented and corrected

- Added authenticated `GET /api/v1/models` and `POST /api/v1/models/select` controls for the existing Qwen 3.8 MLX model and downloaded Qwen 2.5 7B GGUF model. Model IDs select trusted host profiles; file paths, server addresses and credentials are not accepted from the browser.
- Model loading blocks new runs and concurrent changes. Active runs and context planning reject model changes. A failed load leaves execution blocked and permits retry. The selected model ID is saved locally.
- The host manages model processes it starts. Existing matching local endpoints are reused. Initial model loading begins after the host starts listening, so the app can show its loading state immediately.
- Shared Python token-counter references are replaced atomically, so R0, Source, Runtime, PDF and final request budgets all use the new model. Added pinned `lmstudio==1.5.0` for the installed LM Studio tokenizer and prompt-template APIs. Tools and tool-result history are retained in template rendering.
- Cline canonical conversation history is restored through public `readMessages` and `start.initialMessages` when the runtime is recreated. Model changes preserve context deduplication metadata. The final gate recounts restored messages using the selected model.
- Added launcher-only `POST /api/v1/auth/launch-code` using the internal bearer token. It reissues a one-time browser code without replacing the host, sessions or active runs. The response is not cached.
- Added optional `Workspace.display_path` for the Figma project sidebar, abbreviating the user's home with `~`. `root_path` remains an input field.
- Workspace registration now rejects folders overlapping the app's internal data folder before creating an unusable workspace, matching the Python service policy.
- Fixed llama.cpp tool grammar failure: large string `maxLength` generation hints overflowed the installed llama.cpp grammar parser. The OpenAI-compatible provider projection removes these hints from tool definitions before counting and sending. The SDK and executor retain their original schemas and validation; the exact gate counts precisely the body sent.

- Fixed automatic R0 dependency selection: expanded candidates now precede their atomic anchor, with atomic fallback when the whole dependency bundle exceeds the budget. Full symbol boundaries are compared across history and retained material, so a previously included function cannot hide newly discovered helper and constant definitions. Inserted fragments include file/line labels and all actual symbol citations.
- Fixed queued indexing races: the API records the submitted Future and reports `queued` until the sole build worker starts. Repeated start requests reuse the pending job.
- Tool execution summaries now report original produced bytes from the streaming executor, including a capped capture, instead of the small pointer descriptor size.
- Model controls now use the shared JSON Schema, generated TypeScript and browser/host validators. The LM Studio token-count method is included in the same contract; missing this enum previously let selection succeed but blocked the final model request.

- Replaced CLI-only LM Studio cold loading with the pinned official JS SDK (`@lmstudio/sdk@2.1.0`) and its AbortSignal. Shutdown cancels in-flight model selection before awaiting the HTTP listener, releases only acquired model handles, and guards post-shutdown activation. Tests cover pending and immediate cancellation, completion racing with cancellation, and the assembled HTTP shutdown path. The installed server's cancellation channel was also exercised using an isolated instance of its small existing embedding model; cancellation succeeded, the probe was absent afterward, and pre-existing instances were unchanged.
- Fixed citation deduplication across different symbols of one bundle. Snapshot expansion also restores related locations from already saved runs. The actual CUA run was checked: its SDK input contains the function, helper and constant, and the corrected snapshot yields `billing.py`, `helpers.py`, `constants.py`, and the separately retrieved `Invoice.java` candidate.

## Verification

| Check | Result |
| --- | --- |
| Host full suite after model, history and grammar changes | 129 passed, 0 failed |
| Host model HTTP boundary and exact gate | 17 passed, both llama.cpp and LM Studio methods accepted |
| Shared contract suite including model schemas and LM Studio method | 246 passed |
| R0 dependency and index queue integration | 13 passed, including atomic history and explicit selection cases |
| Host workspace registration regression after early overlap refusal | 6 passed, 0 failed |
| Python full suite after R0 and queue corrections | 501 passed, 1 opt-in live test skipped |
| Python ruff, format, mypy, docstring checks | PASS |
| Host TypeScript, ESLint and structure checks | PASS |
| SDK recreation history test | Previous Korean user message and assistant reply present in next outbound request; final gate invoked |
| Actual LM Studio plain request token count | 59 counted = 59 reported by provider |
| Actual LM Studio request with tool definition | 308 = 308 |
| Actual LM Studio request with tool call and result history | 351 = 351 |
| Actual API switch MLX → GGUF → MLX | Both selections returned 200/ready; settings and shared token counter matched selected model |
| Identical Korean text across selected tokenizers | GGUF 6 tokens, MLX 4 tokens, both exact |
| Launcher authentication renewal | 200 with fresh one-time code, existing host retained |
| Actual Qwen 2.5 complete tool schema after compatibility fix | `finish_reason=tool_calls`, `run_command({command:"pwd"})`; no grammar error for the request |

The primary agent reran the final actual Qwen 2.5 smoke after the grammar fix: 12/12 passed, including approved command execution, Runtime Pointer search and PDF page tools. Its input measurements and final UI/desktop acceptance are recorded separately in `artifacts/verification/localdesk-mac/` and the final acceptance report.

Exact counts above are measurements against this Mac's installed runtimes and configured models. Unsupported model framing remains blocked; no character-length heuristic or raw-output fallback was added.
