# Pointer Contracts (task 4.2)

Machine-readable source of truth: `contracts/pointers/*.schema.json`.
Generated TypeScript types: `contracts/generated/ts/contracts.ts` (do not edit by hand).
All payloads carry `schema_version: "1"`.

## 1. Pointer URI

    securecode://runtime/{workspace_id}/{session_id}/{pointer_id}?v=1
    securecode://source/{workspace_id}/{source_id}?v={revision}

- A pointer is an opaque handle. It never contains a file path or a command.
- A consumer must not derive storage paths from a pointer.
- The registry resolves a pointer to an internal object. An unknown or
  malformed pointer returns `INVALID_POINTER`.
- Validation order: (1) URI shape, (2) workspace scope, (3) session scope for
  runtime pointers, (4) existence, (5) expiry or revision.
- A pointer from another workspace or session returns `FORBIDDEN`.

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

| Limit | Value | Status |
|---|---|---|
| `max_bytes` | at most 16384 | roadmap 0.6 |
| `max_tokens` | at most 32768 | roadmap 0.6 |
| `cursor` length | at most 512 characters | draft |

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

| Limit | Value | Status |
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