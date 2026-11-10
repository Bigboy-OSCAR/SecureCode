/**
 * [fixture] Context-service stand-in for route and SDK tests that do not start the Python service.
 * Test-only: production always uses HttpContextServiceClient. It keeps registered workspace roots,
 * serves Source reads/searches of workspace files with contract-shaped results (byte caps, exact
 * selection), answers an empty context plan and reports R0/PDF as not indexed or unavailable.
 */
import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type {
    ContextSelectRequest,
    ContextSelectResponse,
    IndexStatusResponse,
    PointerReadResult,
    ServiceHealthResponse,
    SourceMutationResult,
} from "@securecode/contracts";
import { ContextServiceError } from "../../src/context-client/contextServiceError.js";
import type { ContextServiceClient } from "../../src/context-client/ports.js";

const unavailable = (what: string) => () =>
    Promise.reject(new ContextServiceError("SERVICE_UNAVAILABLE", `${what} is not available in this fixture`, false));

function emptyPlan(request: ContextSelectRequest): ContextSelectResponse {
    const costs = request.costs;
    const fixed = costs.reserved_output_tokens + costs.safety_margin_tokens + costs.message_overhead_tokens;
    const budget = Math.max(0, costs.model_context_limit - fixed);
    return {
        schema_version: "1",
        run_create_error: request.input.context_refs.length > 0 ? "NOT_FOUND" : null,
        plan: {
            schema_version: "1",
            index_revision: request.input.index_revision,
            preview_digest: "0".repeat(64),
            omissions_truncated: false,
            selected: [],
            fragments: [],
            omitted: [],
            budget: {
                budget_tokens: budget,
                used_tokens: 0,
                count_mode: "provider_estimate",
                costs: {
                    model_context_limit: costs.model_context_limit,
                    system_tokens: 0,
                    tool_schema_tokens: 0,
                    prompt_tokens: 0,
                    history_tokens: 0,
                    message_overhead_tokens: costs.message_overhead_tokens,
                    reserved_output_tokens: costs.reserved_output_tokens,
                    safety_margin_tokens:
                        costs.model_context_limit -
                        budget -
                        costs.reserved_output_tokens -
                        costs.message_overhead_tokens,
                },
            },
        },
    };
}

export function createFixtureContextClient(): ContextServiceClient {
    const roots = new Map<string, string>();
    const files = new Map<string, { root: string; path: string }>();
    const status = (workspaceId: string): IndexStatusResponse =>
        ({
            schema_version: "1",
            workspace_id: workspaceId,
            index_status: "not_indexed",
            index_revision: null,
            searchable: false,
            counts: { files: 0, symbols: 0, skipped: 0 },
            diagnostics: [],
        }) as unknown as IndexStatusResponse;
    const pointerOf = (workspaceId: string, path: string) =>
        `securecode://source/${workspaceId}/src_${createHash("sha256").update(path).digest("hex").slice(0, 24)}?v=1`;
    const fileOf = (pointer: string) => {
        const file = files.get(pointer);
        if (!file) throw new ContextServiceError("NOT_FOUND", "pointer not registered", false);
        return file;
    };
    return {
        health: () =>
            Promise.resolve<ServiceHealthResponse>({
                schema_version: "1",
                service: "context-service",
                status: "ok",
                version: "0.1.0",
                components: [
                    { name: "token_counter", status: "ok" },
                    { name: "data_dir", status: "ok" },
                ],
            }),
        tokens: { count: unavailable("tokens.count"), countRequest: unavailable("tokens.request") },
        context: { select: (request) => Promise.resolve(emptyPlan(request)) },
        symbols: { search: unavailable("symbols.search"), readBundle: unavailable("symbols.bundle") },
        workspaces: {
            register: (workspaceId, rootPath) => {
                roots.set(workspaceId, rootPath);
                return Promise.resolve();
            },
            startIndex: (workspaceId) => Promise.resolve(status(workspaceId)),
            indexStatus: (workspaceId) => Promise.resolve(status(workspaceId)),
        },
        sources: {
            mutate: (workspaceId, request) => {
                const root = roots.get(workspaceId);
                if (!root || request.operation !== "register") return unavailable("source.refresh")();
                const path = request.target.path;
                const pointer = pointerOf(workspaceId, path);
                files.set(pointer, { root, path });
                const result = { schema_version: "1", items: [{ pointer }] } as unknown as SourceMutationResult;
                return Promise.resolve(result);
            },
            read: (_workspaceId, request) => {
                const { root, path } = fileOf(request.pointer);
                const data = readFileSync(join(root, path));
                const max = request.max_bytes ?? 16 * 1024;
                let end = Math.min(data.length, max);
                while (end > 0 && end < data.length && ((data[end] ?? 0) & 0xc0) === 0x80) end -= 1;
                const result: PointerReadResult = {
                    schema_version: "1",
                    pointer: request.pointer,
                    content: data.subarray(0, end).toString("utf8"),
                    provenance: {
                        media_type: "text/plain",
                        byte_size: statSync(join(root, path)).size,
                        revision: 1,
                        ...(end > 0
                            ? {
                                  selection: {
                                      revision: 1,
                                      content_sha256: createHash("sha256").update(data).digest("hex"),
                                      range: { type: "byte", start: 0, end },
                                  },
                              }
                            : {}),
                    },
                    truncated: end < data.length,
                    token_count: end,
                    count_mode: "provider_estimate",
                };
                return Promise.resolve(result);
            },
            search: unavailable("source.search"),
            list: unavailable("source.list"),
            unregister: unavailable("source.unregister"),
        },
        runtime: { list: unavailable("runtime.list"), remove: unavailable("runtime.remove") },
        pdf: {
            parse: unavailable("pdf.parse"),
            status: unavailable("pdf.status"),
            readPages: unavailable("pdf.read"),
            search: unavailable("pdf.search"),
        },
    };
}
