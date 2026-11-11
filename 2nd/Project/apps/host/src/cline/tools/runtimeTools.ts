/**
 * runtime_read / runtime_search: bounded reads of this session's Runtime Pointers through the
 * 4.3 contract routes (selector, byte/token caps, scoped cursor). Their results are bounded by the
 * service caps and are never stored again by the transformer (bounded-read policy).
 */
import type { AnswerCitation, PointerReadRequest, PointerSearchRequest } from "@securecode/contracts";
import type { RuntimePointerService, RuntimeScope } from "../adapter/ports.js";
import { turnStorage } from "../adapter/turnContext.js";
import { ContextServiceError } from "../../context-client/contextServiceError.js";
import { objectSchema, review, type ProjectTool } from "./toolSupport.js";

const READ_MAX_BYTES = 16 * 1024;
const READ_MAX_TOKENS = 32 * 1024;
/** Room kept for the tool_result framing around a read when sizing it to the request budget. */
const TOOL_RESULT_FRAMING_TOKENS = 256;
const SEARCH_LIMIT = 50;

export interface RuntimeToolOptions {
    service: RuntimePointerService;
    scope: RuntimeScope;
    timeoutMs: number;
    /** Records only the confirmed range returned by a successful bounded read. */
    readonly recordCited: (citation: AnswerCitation) => void;
}

const selectorSchema = {
    type: "object",
    properties: {
        type: { type: "string", enum: ["line", "byte", "section", "json_path"] },
        start: { type: "integer", minimum: 0 },
        end: { type: "integer", minimum: 0 },
        section: { type: "string", minLength: 1, maxLength: 256 },
        path: { type: "string", minLength: 1, maxLength: 512 },
    },
    required: ["type"],
    additionalProperties: false,
};

function record(input: unknown): Record<string, unknown> {
    if (typeof input !== "object" || input === null || Array.isArray(input))
        throw new Error("tool input must be an object");
    return input as Record<string, unknown>;
}

/** Service errors become a short coded message; no stored content is echoed. */
async function guarded<T>(work: () => Promise<T>): Promise<T> {
    try {
        return await work();
    } catch (error) {
        if (error instanceof ContextServiceError) {
            throw new Error(`${error.code}: ${error.message}`, { cause: error });
        }
        throw error;
    }
}

function signalFor(options: RuntimeToolOptions, signal: AbortSignal | undefined): AbortSignal {
    const timeout = AbortSignal.timeout(options.timeoutMs);
    return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

/**
 * Token cap for a read so its result still fits the next model request (4.8): the window left after the
 * last allowed request, minus room for the tool_result framing. Null when no request was counted yet.
 */
export function readTokenCap(): number | null {
    const remaining = turnStorage.getStore()?.remainingRequestTokens;
    if (remaining === undefined) return null;
    const cap = Math.min(READ_MAX_TOKENS, remaining - TOOL_RESULT_FRAMING_TOKENS);
    if (cap < 1) {
        throw new Error("BUDGET_EXCEEDED: the model window has no room for more output; start a new session");
    }
    return cap;
}

export function runtimeReadTool(options: RuntimeToolOptions): ProjectTool {
    return {
        requiresApproval: false,
        review: () => review("other", "read runtime pointer", ""),
        refuse: () => null,
        tool: {
            name: "runtime_read",
            description:
                "Read part of a stored tool output (Runtime Pointer) of this session. Use selector " +
                "{type:'line',start,end} / {type:'byte',start,end} / {type:'section',section} / {type:'json_path',path}, " +
                "and pass next_cursor back as cursor to continue. At most 16 KiB per call.",
            inputSchema: objectSchema(
                {
                    pointer: { type: "string" },
                    selector: selectorSchema,
                    max_bytes: { type: "integer", minimum: 1, maximum: READ_MAX_BYTES },
                    cursor: { type: "string", minLength: 1, maxLength: 512 },
                },
                ["pointer"],
            ),
            execute: async (input, context) => {
                const request = record(input) as Omit<PointerReadRequest, "schema_version">;
                const cap = readTokenCap();
                if (cap !== null) request.max_tokens = Math.min(request.max_tokens ?? cap, cap);
                const result = await guarded(() =>
                    options.service.read(options.scope, request, signalFor(options, context.signal)),
                );
                const selection = result.provenance.selection;
                if (selection) options.recordCited({ ref: { kind: "runtime", pointer: result.pointer, selection } });
                return JSON.stringify({
                    content: result.content,
                    truncated: result.truncated,
                    next_cursor: result.next_cursor ?? null,
                    range: result.provenance.selection?.range ?? null,
                    token_count: result.token_count,
                });
            },
        },
    };
}

export function runtimeSearchTool(options: RuntimeToolOptions): ProjectTool {
    return {
        requiresApproval: false,
        review: () => review("other", "search runtime pointer", ""),
        refuse: () => null,
        tool: {
            name: "runtime_search",
            description:
                "Search a stored tool output of this session for a literal string (case-sensitive). Returns line " +
                "numbers, byte offsets and short snippets; pass next_cursor back as cursor to continue.",
            inputSchema: objectSchema(
                {
                    pointer: { type: "string" },
                    query: { type: "string", minLength: 1, maxLength: 256 },
                    limit: { type: "integer", minimum: 1, maximum: SEARCH_LIMIT },
                    cursor: { type: "string", minLength: 1, maxLength: 512 },
                },
                ["pointer", "query"],
            ),
            execute: async (input, context) => {
                const request = record(input) as Omit<PointerSearchRequest, "schema_version">;
                const result = await guarded(() =>
                    options.service.search(options.scope, request, signalFor(options, context.signal)),
                );
                return JSON.stringify({
                    matches: result.matches.map((match) => ({
                        line: match.line,
                        byte_offset: match.byte_offset,
                        content: match.content,
                    })),
                    truncated: result.truncated,
                    next_cursor: result.next_cursor ?? null,
                });
            },
        },
    };
}
