# Pointer Contracts (task 4.2)

Machine-readable source of truth: `contracts/pointers/*.schema.json`.
Generated TypeScript types: `contracts/generated/ts/contracts.ts` (do not edit by hand).
All payloads carry `schema_version: "1"`.

## 1. Pointer URI

    securecode://runtime/{workspace_id}/{session_id}/{pointer_id}?v=1
    securecode://source/{workspace_id}/{source_id}?v={revision}

- The URI contains the documented workspace and session ID components, an opaque object ID made of ASCII letters, digits, underscores or hyphens, and a positive revision. Runtime handles use version 1. The URI kind must match the descriptor or context reference kind.
- A consumer must not derive storage paths from a pointer.
- The registry resolves a pointer to an internal object. An unknown or
  malformed pointer returns `INVALID_POINTER`.
- Validation order: (1) URI shape, (2) workspace scope, (3) session scope for
  runtime pointers, (4) existence, (5) expiry or revision.
- The service compares the URI scope and revision with the authenticated request and registry record. Another workspace or session returns `FORBIDDEN`. Shape validation alone cannot authorize a read.

## 2. Descriptor rules

| Field | Runtime | Source |
|---|---|---|
| `session_id` | required | forbidden |
| `expires_at` | required (TTL 24h by default) | not present |
| `revision` | integer >= 1 | integer >= 1, changes when the source changes |
| `preview` | at most 512 UTF-8 bytes | at most 512 UTF-8 bytes |

`available_operations` lists the operations the pointer supports (`read`, `search`).

## 3. Selectors

| Selector | Index base | End of range |
|---|---|---|
| `line` | 1 | inclusive |
| `pdf_page` | 1 | inclusive |
| `byte` | 0 | exclusive, `[start, end)` |
| `section` | not applicable | whole named section |
| `json_path` | not applicable | value at the path |

- JSON Schema cannot compare two fields. The schema checks each value's range
  only. The service must reject `end < start` with `INVALID_SELECTOR`
  (`details.reason = "end_before_start"`).
- A byte range must not split a UTF-8 character. The service returns the
  longest valid prefix and sets `truncated = true`.
- A selector that does not fit the media type returns `INVALID_SELECTOR`.

## 4. Read

Request: `pointer`, optional `selector`, `max_bytes`, `max_tokens`, `cursor`.
Result: `content`, `provenance`, `truncated`, `next_cursor`, `token_count`, `count_mode`.

| Limit | Value | Contract |
|---|---|---|
| `max_bytes` | at most 16384 bytes | roadmap 0.7 |
| `max_tokens` | at most 32768 tokens | roadmap 0.7 |
| `cursor` length | at most 512 characters | `OpaqueCursor` in common/primitives.schema.json |

- The shared validators enforce a maximum of 16,384 UTF-8 bytes per read content string or search snippet and 512 UTF-8 bytes per descriptor preview. The producer must also enforce the requested byte and token limits across the returned material.
- When the result is cut by a cap, `truncated = true` and `next_cursor` is set
  if more content exists.
- `count_mode` states how `token_count` was produced
  (`exact`, `provider_estimate`, `provider_reported`).

## 5. Cursor

A cursor is bound to the pointer, its scope, its revision and the query that
created it. A cursor used against a different pointer, session or query returns
`INVALID_POINTER`. A cursor whose source revision changed returns `SOURCE_CHANGED`.

## 6. Search (`runtime.search`, `source.search`)

Request: `pointer`, `query`, optional `limit`, `cursor`, `max_bytes`, `max_tokens`.
Result: `matches` (each with `line`, `content`, `byte_offset`), `truncated`,
`next_cursor`, `token_count`, `count_mode`.

| Limit | Value | Contract |
|---|---|---|
| `query` length | at most 256 characters | draft |
| `limit` | at most 100 | draft |

- The query is a plain string pattern. It is never executed as a command.
- The service bounds the scan by bytes and time. When the scan limit is
  reached, the result sets `truncated = true` and `next_cursor`.
- Every match reports the line number and byte offset it came from.
- No match is not an error: the response is HTTP 200 with an empty `matches`
  list (error code `NO_MATCH`, transport `success_body`).

Values marked draft come from task 4.2 and may be tuned by tasks 4.3 and 4.6
when they measure real behavior. A change must update the schema, the fixtures
and this table together.

## 7. Errors

| Code | HTTP | retryable | Meaning for the UI |
|---|---|---|---|
| `INVALID_POINTER` | 400 | false | The pointer or cursor is malformed or not usable. |
| `FORBIDDEN` | 403 | false | The pointer belongs to another workspace or session. |
| `NOT_FOUND` | 404 | false | The pointer or source does not exist or was deleted. |
| `EXPIRED` | 410 | false | The runtime pointer passed its TTL. It will not return. |
| `SOURCE_CHANGED` | 409 | false | The source changed. Read it again to get the new revision. |
| `INVALID_SELECTOR` | 400 | false | The range does not fit the media type or is reversed. |
| `UNSUPPORTED_FORMAT` | 415 | false | The content type cannot be read by this operation. |
| `PARSE_FAILED` | 422 | false | A PDF or document could not be parsed. |
| `BUDGET_EXCEEDED` | 413 | false | The request exceeds a byte or token limit. |

`retryable` means the same request may succeed if sent again unchanged.
`BUDGET_EXCEEDED` is false because the caller must send a smaller request.
`QUOTA_EXCEEDED` is final for status and retryability (HTTP 507, not retryable). The numeric storage limits are measured by task 4.3.

## 8. Source lifecycle

- `source.unregister` removes only the service registration and service-owned
  derived data. It never deletes or modifies the user's original file.
- A source whose file changed moves to `changed`. Reads with the old revision
  return `SOURCE_CHANGED`.

## 9. Ports for later tasks

| Task | Uses |
|---|---|
| 2.2, 1.x | `PointerDescriptor`, error table above |
| 3.3, 3.5 | `RuntimePutRequest`, `PointerReadRequest`, `PointerReadResult` |
| 4.3 | Runtime store: `RuntimePutRequest`, read, search, descriptor |
| 4.5 | `SourceRegistration`, descriptor |
| 4.7 | `PointerDescriptor`, `PointerReadResult` as context inputs |

## 10. Public operations consumed by the UI

These are version-1 wire contracts for 2.2 screen design and fixture validation. The route catalog records when each handler will be connected. The host authenticates the user on every request and checks the workspace, runtime session and expected revision against its registry, including before acknowledging a replay of a write.

| Method and path (under `/api/v1`) | Request | Success |
| --- | --- | --- |
| GET `/workspaces/:id/pointers` | `PointerListQuery` decoded from query parameters | 200 `PointerListResult` |
| POST `/workspaces/:id/sources` | `SourceMutationRequest`, operation `register` or `refresh` | 200 `SourceMutationResult` |
| DELETE `/pointers` | `PointerDeleteRequest` JSON body | 200 `PointerDeleteResult` |
| POST `/pdf/parse` | `PdfParseRequest` for a registered PDF Source URI | 200 `PdfJobStatus`, including existing jobs on replay |
| GET `/pdf/jobs/:job_id` | Opaque ID returned by parse | 200 current `PdfJobStatus` |

**Listing.** The user chooses a Source or Runtime tab. Send `kind=source` for the workspace or `kind=runtime&session_id=…` for one authorized session. The optional `limit` defaults to 20 (1–100). Reuse `page.next_cursor` only with the same workspace, kind and session. Public list items include a safe `display_name` and `supported_selectors`. Workspace Sources may expose a `relative_path`. External Sources and Runtime outputs expose a display label only. Unknown legacy descriptor capabilities have no enabled selector until a public item is retrieved.

**Registration and refresh.** Accept a single explicitly chosen file or directory per request. Workspace targets contain a project-relative path. External targets contain a user-confirmed absolute local file or directory, submitted only in the authenticated request body. A path string never grants authorization. The host restricts traversal to the approved root, checks symlinks/junctions and rejects parent traversal and device or network paths. Issue diagnostics name only paths relative to the selected root. For a directory, the response lists the registered files and each excluded file with its reason. An empty directory succeeds with two empty arrays. A top-level failure returns an error envelope. More than 100 entries beneath the chosen root requires a narrower selection (`PAYLOAD_TOO_LARGE`) before committing registrations. A file-level failure in a directory produces `partial`; each entry is represented exactly once in either `items` or `issues`. For a single file failure, use the error envelope. `refresh` acts on the identified registration in its workspace, rechecks the original authorization and returns its current descriptor. A changed file has a new versioned URI. Old selections, cursors and previews must be discarded, and the user re-reads and reselects the new range.

**Deletion and recovery.** Successful Source deletion returns `effect=unregistered` and invalidates the registration, its derived cache and selections. The original disk file is preserved. `effect=runtime_deleted` removes one stored output of the named workspace/session. Only the explicit confirmation submits the request. On an uncertain response, retry the same method, body and idempotency key in the same scope to recover the original outcome. Reusing a key with altered input is a conflict. A new delete request for an already absent target can acknowledge the same effect after authorization; callers never infer another session's object existence. After a write, re-list the same scope.

**Selector input.** Offer the intersection of `available_operations` and `supported_selectors` advertised by the server. UTF-8 text supports byte/line views. Markdown can additionally advertise `section`: enter the exact case-sensitive heading text (1–256 characters, without leading Markdown heading markers); the section extends to the next heading at the same or higher level. A missing or ambiguous heading yields `INVALID_SELECTOR`. For JSON that fits the structured-read cap, `json_path` takes a slash-prefixed JSON Pointer (1–512 characters; `~0` for tilde and `~1` for slash, zero-based decimal array indexes). Expressions, wildcards and recursive evaluation are unsupported. The service checks the path against the document and returns `INVALID_SELECTOR` if it cannot be resolved. Larger JSON can still advertise bounded line/byte views. PDF page selection becomes available after confirmed page extraction.

## 11. Confirming the displayed range

A selectable nonempty read includes `PointerReadResult.provenance.selection`, a `PointerSelection`. Each selectable search snippet carries its own `matches[].selection`. The selection contains the object revision, SHA-256 of the original file or stored output, and the exact half-open UTF-8 byte interval of the returned text. For a document `range.type=byte`, offsets are in the original bytes. A section or JSON value is selectable only as its exact source slice. For `type=pdf_page`, `page` is 1-based and byte offsets address that page's extracted UTF-8 text with the stated `parser_version`. Read at most one PDF page per selectable fragment; the next cursor continues the same request. `provenance.byte_size` reports total original object bytes. A relative project path or safe display name may accompany provenance.

A producer validates `0 <= start < end`, valid UTF-8 boundaries, matching URI scope/revision and original hash, current PDF parser version where applicable, and `end - start == byteLength(content)`. Empty, legacy or unverifiable output stays viewable but cannot supply an explicit selection. For a cut line, JSON value or page, confirm just the displayed interval. For a run or preview send back that exact selection, including its hash and revision. The server authorizes and verifies it again and applies the output and token budgets before returning source bytes. If the new budget cannot hold it, show the omission or obtain confirmation for a smaller range. A stale range cannot fall back to a whole file.

## 12. PDF display and recovery

The parse request carries a registered Source pointer with its revision, workspace, and an idempotency key. Repeating the same submission returns the same job ID, including after a lost POST response. Poll its GET route after reconnecting. A worker may return an existing job for the same source hash and parser version. A changed source requires a refresh, then a new parse submission with a new key. An expired or removed registration is handled through the common error envelope.

| Job state | Screen and allowed actions |
| --- | --- |
| `queued`, `running` | Show indeterminate progress and recheck the job. Registration success alone does not enable page reading. |
| `ready` | Pages 1 through `page_count` are readable for this hash, URI revision and parser version. Page reads still require scope and byte/token checks. |
| `partial` | Exclude every page in `excluded_pages` (empty, scanned or unreadable). Other pages may be read. The service returns distinct page numbers in the advertised range and at least one readable page. |
| `unsupported` | Show the confirmed reason (scanned, empty, encrypted, over the page/size cap, or unsupported format). Offer a different document or a smaller file. |
| `failed` | Show damaged, timeout or parse failure. A new user-requested attempt gets a new key. HTTP/network errors without a job state do not prove that parsing failed. |
| `stale` | Source or parser changed. Invalidate selections and disable cached pages until reprocessing succeeds. |

A ready or partial status returns page count, hash and parser version, with no extracted body. Unsupported, failed and stale jobs expose no readable pages. UI fixtures cover these wire states in `contracts/fixtures/pointers/pdf-*.json`. Actual extraction, jobs and tool execution have separate implementation acceptance.
