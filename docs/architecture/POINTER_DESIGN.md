# Runtime and Source Pointer Integrated Design

## Purpose

This document defines Runtime Pointers, Source Pointers, PDF Source Pointers, lifecycle, storage policy, SDK integration boundary, and the minimum service interface handed to task 3.2.

A pointer is an opaque, scoped, revocable reference to contextual data.

## Non-goals

This design does not introduce RAPTOR, summarization trees, H LLM selectors, embeddings, or Self-Extend.

Context Selector and PDF handling are orchestration and extraction layers over R0 TF-IDF Symbol Bundle, Source Pointer, and Runtime Pointer mechanisms.

## Pointer kinds

| Kind | Scope | Storage | Lifecycle |
|---|---|---|---|
| Runtime Pointer | workspace + session | SQLite metadata and blob storage | put, ready, read, expired, deleted |
| Source Pointer | workspace | Source registry and filesystem source root | register, ready, changed, unregistered |
| PDF Source Pointer | workspace | Source registry, parsed PDF cache, original PDF | parsing, ready, unsupported, failed |

## Scope and isolation

- Every pointer belongs to a workspace.
- Runtime Pointers additionally belong to a session.
- Pointer IDs are opaque UUIDs.
- Clients must not derive storage paths or internal keys from pointer IDs.
- Runtime data is isolated by workspace and session.
- Source data is isolated by workspace.
- Every read validates workspace and session scope.

## URI format

    securecode://runtime/{workspace_id}/{session_id}/{pointer_id}?v=1
    securecode://source/{workspace_id}/{source_id}?v={revision}

- Pointer URIs are opaque.
- v is a revision or fingerprint marker.
- Runtime URIs include workspace and session scope.
- Source URIs include workspace scope and source revision.
- Modified sources produce a new revision.
- Old cursors may return SOURCE_CHANGED.

## Runtime Pointer lifecycle

    put -> ready -> read -> expired/deleted

Operations:

- put
- stat
- list
- read
- search
- delete
- clear_session

Storage policy:

- Metadata is stored in SQLite.
- Content blobs are stored outside SQLite.
- Writes publish metadata and blob atomically.
- Incomplete writes are not exposed as valid pointers after restart.
- TTL enables expiration and cleanup.
- Expired pointers return EXPIRED.
- Deleted or unknown pointers return NOT_FOUND.

Runtime limits:

| Policy | Default |
|---|---|
| Runtime TTL | 24 hours |
| Runtime objects per session | 10,000 |
| Pointer preview | 512 UTF-8 bytes |
| Raw tool-result payload cap | 16 KiB |
| Read token cap | 32 KiB tokens |
| Runtime quota per session | 32 MiB |
| Runtime quota per workspace | 128 MiB |

## Source Pointer lifecycle

    register -> ready -> changed/unregistered

Operations:

- register
- stat
- list
- read
- search
- unregister

Source protection policy:

- The Context Service never deletes a user original source file.
- unregister removes only service metadata and service-owned derived artifacts.
- PDF parsed text is a derived cache and may be rebuilt from the original PDF.
- Source roots use real-path resolution.
- Symlink traversal and dot-dot escapes outside the workspace source root are rejected.
- Fingerprint and revision detect external modification.

Source limits:

| Policy | Default |
|---|---|
| Source quota per workspace | 256 MiB |
| JSON source size limit | 8 MiB |
| PDF size limit | 50 MiB |
| PDF page limit | 500 pages |
| Read buffer | Bounded streaming read |

## PDF Source Pointer lifecycle

    register/parse -> parsing -> ready/unsupported/failed

- parsing means a PDF parse job is active.
- ready means extracted text and page metadata are available.
- unsupported means the PDF cannot be processed.
- failed means parsing failed.
- PDF reads are bounded by page selector, byte cap, and token cap.
- PDF provenance includes source hash, parser version, and page range.

## Selectors and bounded reads

Supported selectors:

- line
- byte
- section
- json_path
- pdf_page

Rules:

- Byte offsets start at zero.
- Line numbers start at one.
- Reads enforce max_bytes and max_tokens.
- Truncated responses set truncated=true.
- Applicable responses include next_cursor.
- Selectors are validated against pointer media type.

## SDK integration boundary

### ToolResultTransformer

ToolResultTransformer runs in the SDK host through afterTool.

- The SDK host passes the original tool result to the Context Service when available.
- If the SDK truncated the result before the hook, the service stores only available content and marks provenance as truncated.
- If output exceeds the threshold, the service creates a Runtime Pointer.
- The service returns a compact PointerDescriptor.
- The SDK appends the descriptor to canonical history through appendContext.

### ModelRequestGate

ModelRequestGate runs in the SDK host through beforeModel.

- It materializes selected pointer fragments into the outbound provider payload.
- It enforces the model context budget.
- It accounts for system prompt, tool schemas, user messages, retained history, message overhead, reserved output tokens, and safety margin.
- If exact tokenization is unavailable, it fails closed with TOKENIZER_UNAVAILABLE.
- It returns BUDGET_EXCEEDED rather than silently dropping required context.

### Failure and blocking policy

| Condition | Required behavior |
|---|---|
| Hook timeout | Follow configured hookErrorMode; throw blocks the turn |
| Hook error | Never fabricate a pointer; follow hookErrorMode |
| Context Service unavailable | Do not claim pointer creation; surface SDK_UNAVAILABLE or configured fallback |
| Pointer registration missing | Do not append a descriptor; record failure |
| Original result truncated before hook | Store available content only and mark provenance truncated |
| Tokenizer unavailable | Fail closed with TOKENIZER_UNAVAILABLE |
| Budget exceeded | Return BUDGET_EXCEEDED |

## Error model

| Error | Meaning |
|---|---|
| INVALID_POINTER | Pointer URI or descriptor malformed |
| NOT_FOUND | Pointer or source does not exist |
| EXPIRED | Runtime Pointer TTL elapsed |
| FORBIDDEN | Caller lacks scope access |
| SOURCE_CHANGED | Source revision mismatch |
| INVALID_SELECTOR | Selector malformed or unsupported |
| UNSUPPORTED_FORMAT | Content type unsupported |
| PARSE_FAILED | PDF or document parsing failed |
| NO_MATCH | Search found no match |
| BUDGET_EXCEEDED | Byte or token limit exceeded |
| TOKENIZER_UNAVAILABLE | Tokenizer unavailable |
| SDK_UNAVAILABLE | SDK or Context Service unavailable |

## Service boundary handed to 3.2

### Service ports

| Boundary | Responsibility | Required by |
|---|---|---|
| Runtime Pointer Service | Store, inspect, read, search, expire, delete transient output | 4.3, 4.4 |
| Source Pointer Service | Register, inspect, read, search, unregister workspace sources | 4.5, 4.6 |
| PDF Service | Parse PDFs, expose status, provide bounded page reads | 4.9 |
| Context Service | Select and materialize bounded context | 4.7, 4.8 |
| Token Service | Provide exact or estimated token counts | 3.2, 4.8 |

### Minimum operations for 3.2

- runtime.put
- runtime.stat
- runtime.list
- runtime.read
- runtime.search
- runtime.delete
- runtime.clear_session
- source.register
- source.stat
- source.list
- source.read
- source.search
- source.unregister
- context.select
- pdf.parse
- pdf.status
- pdf.read_pages
- tokens.count

### Dependencies required by 3.2

- SQLite-compatible Runtime metadata store
- Blob storage outside the database
- Workspace-scoped Source root
- PDF parser and parser-version-aware cache
- Token counter abstraction
- Context Service HTTP client
- Pointer descriptor and selector contracts

## Restart, concurrency, and cleanup

- Runtime writes use atomic metadata-plus-blob publication.
- After restart, incomplete writes are absent or recovered only when metadata and blob are both valid.
- TTL sweeping removes expired Runtime metadata and blobs.
- Concurrent reads are allowed while a pointer remains valid.
- Concurrent writes to the same Runtime Pointer ID are not expected because each put creates a new ID.
- Source fingerprint checks detect external modification and transition Source Pointers to changed.

## Verification plan

This is a design task, so verification is documentation-consistency review rather than runtime integration testing.

Checks:

- Runtime, Source, and PDF lifecycles are consistent.
- URI scope matches workspace and session isolation.
- Storage, deletion, TTL, quota, and cleanup policies do not conflict.
- SDK hook failure modes define explicit blocking or fallback behavior.
- Minimum service operations and dependencies for 3.2 are identified.
- No RAPTOR, summarization tree, H LLM selector, embedding, or Self-Extend is introduced.
