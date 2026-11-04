# Pointer Design

## Purpose

This document defines the shared design for Runtime Pointers, Source Pointers, and their integration with the Cline SDK.

A pointer is an opaque, revocable reference to contextual data. It lets an agent keep a small descriptor in history while retaining the ability to read bounded content on demand.

## Pointer kinds

| Kind | Scope | Backing storage | Lifecycle |
|---|---|---|---|
| Runtime Pointer | `workspace_id` + `session_id` | SQLite metadata plus blob storage | `ready`, `read`, `expired`, `deleted` |
| Source Pointer | `workspace_id` | Filesystem-backed source registry | `ready`, `changed`, `unregistered` |
| PDF Source Pointer | `workspace_id` | Parsed PDF artifact and source registry | `parsing`, `ready`, `unsupported`, `failed` |

## Scope and isolation

- Every pointer belongs to a workspace.
- Runtime Pointers additionally belong to a session.
- Pointer IDs are opaque UUIDs; clients must not infer storage paths or internal object names from them.
- Runtime data is isolated by `workspace_id` and `session_id`.
- Source data is isolated by `workspace_id`.
- Reads validate workspace and session scope before returning content.

## URI format

Pointers use the `securecode://` scheme.

```text
securecode://runtime/{workspace_id}/{session_id}/{pointer_id}?v=1
securecode://source/{workspace_id}/{source_id}?v={revision}
```

Rules:

- The URI is opaque to UI and SDK consumers.
- `v` is a revision or fingerprint marker used for staleness checks.
- Runtime URIs must include workspace and session scope.
- Source URIs must include workspace scope and source revision.
- A changed source produces a new revision; old cursors may return `SOURCE_CHANGED`.

## Runtime Pointers

Runtime Pointers store transient tool output, command output, logs, or other agent-generated content.

### Operations

- `put`: store content and create a descriptor.
- `stat`: inspect metadata without reading content.
- `list`: enumerate pointers in a workspace or session.
- `read`: return bounded content, optionally with a selector and cursor.
- `search`: perform bounded search over stored runtime content.
- `delete`: remove one pointer.
- `clear_session`: remove all Runtime Pointers for a session.

### Storage

- Metadata is stored in SQLite.
- Content blobs are stored outside the database and addressed by an internal, non-guessable key.
- Writes use atomic rename semantics.
- TTL metadata enables expiration and background sweeping.
- Expired or deleted pointers return `EXPIRED` or `NOT_FOUND`; they do not expose content.

### Limits

- Runtime content is subject to byte and token caps.
- Reads are bounded and may return `truncated=true` plus `next_cursor`.
- A pointer descriptor includes a short preview, not the full content.

## Source Pointers

Source Pointers reference registered files or documents under a workspace source root.

### Operations

- `register`: add a source and compute its fingerprint and revision.
- `stat`: inspect source metadata.
- `list`: enumerate registered sources.
- `read`: read bounded text, JSON, Markdown, log, or PDF content.
- `search`: perform bounded search.
- `unregister`: remove a source registration.

### Safety

- Source roots are resolved with real paths.
- Symlink traversal and `..` escapes outside the workspace source root are rejected.
- Source fingerprint and revision detect modification.
- Reads use bounded IO; large files must not be loaded entirely into memory.

## Selectors

A selector identifies a bounded portion of content.

Supported selector forms:

- `line`: line ranges.
- `byte`: byte ranges.
- `section`: document or Markdown section.
- `json_path`: JSON path.
- `pdf_page`: PDF page ranges.

Rules:

- Byte offsets start at zero.
- Line numbers start at one.
- Reads enforce `max_bytes` and `max_tokens`.
- If content is truncated, the response includes `truncated=true` and, when applicable, `next_cursor`.

## SDK integration

The Cline SDK integration uses two extension points:

### `afterTool`

`ToolResultTransformer` runs after a tool completes.

- If output exceeds the configured threshold, the hook stores the output as a Runtime Pointer.
- It replaces or augments the raw tool result with a compact `PointerDescriptor`.
- The descriptor is appended to canonical SDK history through `appendContext`.
- Hook timeout and error behavior follow the configured `hookErrorMode`.

### `beforeModel`

`ModelRequestGate` runs before a model request.

- It can materialize selected pointer fragments into the outbound provider payload.
- It enforces the model context budget.
- It accounts for system prompt, tool schemas, user messages, retained history, message overhead, reserved output tokens, and safety margin.
- If tokenization is unavailable, the gate fails closed with `TOKENIZER_UNAVAILABLE`.

## Error model

| Error | Meaning |
|---|---|
| `INVALID_POINTER` | Pointer URI or descriptor is malformed. |
| `NOT_FOUND` | Pointer or source does not exist. |
| `EXPIRED` | Runtime Pointer TTL has elapsed. |
| `FORBIDDEN` | Caller lacks access to the requested scope. |
| `SOURCE_CHANGED` | Source revision no longer matches the pointer or cursor. |
| `INVALID_SELECTOR` | Selector is malformed or unsupported for the media type. |
| `UNSUPPORTED_FORMAT` | Content type cannot be read by the requested operation. |
| `PARSE_FAILED` | PDF or document parsing failed. |
| `NO_MATCH` | Search found no matching content. |
| `BUDGET_EXCEEDED` | Requested content exceeds byte or token limits. |

## Relationship to later tasks

- 4.2 defines the concrete JSON contracts and selector schema.
- 4.3 implements the Runtime Pointer store.
- 4.4 implements the Cline Runtime Pointer hook.
- 4.5 implements Source registration and lifecycle.
- 4.6 implements bounded Source readers and search.
- 4.7 and 4.8 implement Context Selector and model gating.
- 4.9 implements PDF Source Pointers and the PDF skill.
