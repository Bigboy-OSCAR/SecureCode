/**
 * Source-backed file tools (3.6): read_file and search_file never open files in the host. The host only
 * checks the path is inside the workspace (no links, .git or .securecode); the context-service registers
 * the file as a Source Pointer (idempotent), re-checks scope and identity, and returns one bounded range
 * with its provenance (revision, SHA-256, exact range). Returned ranges are recorded as shown so the
 * Selector never inserts them again.
 */
import { createHash } from "node:crypto";
import type { AnswerCitation, ExplicitContextRef, PointerReadResult } from "@securecode/contracts";
import { ContextServiceError } from "../../context-client/contextServiceError.js";
import type { SourceService } from "../../context-client/workspaceServices.js";
import { readTokenCap } from "./runtimeTools.js";
import { field, objectSchema, review, type ProjectTool } from "./toolSupport.js";
import { resolveForRead, toRelative } from "./workspacePaths.js";

const READ_MAX_BYTES = 16 * 1024;
const SEARCH_LIMIT = 50;

export interface SourceToolOptions {
    sources: SourceService;
    workspaceId: string;
    root: string;
    timeoutMs: number;
    /** Records a range whose raw text the model has now seen. */
    recordShown(ref: ExplicitContextRef): void;
    recordCited(citation: AnswerCitation): void;
}

function input(value: unknown): Record<string, unknown> {
    if (typeof value !== "object" || value === null || Array.isArray(value))
        throw new Error("tool input must be an object");
    return value as Record<string, unknown>;
}

function positive(value: unknown, name: string): number | undefined {
    if (value === undefined) return undefined;
    if (typeof value !== "number" || !Number.isInteger(value) || value < 1)
        throw new Error(`tool input field "${name}" must be a positive integer`);
    return value;
}

async function guarded<T>(work: () => Promise<T>): Promise<T> {
    try {
        return await work();
    } catch (error) {
        if (error instanceof ContextServiceError) {
            const reason = typeof error.details?.reason === "string" ? ` (${error.details.reason})` : "";
            throw new Error(`${error.code}${reason}: ${error.message}`, { cause: error });
        }
        throw error;
    }
}

/** Registers (idempotently) the workspace file as a Source and returns its current pointer. */
async function pointerFor(
    options: SourceToolOptions,
    path: string,
    signal: AbortSignal,
): Promise<{ rel: string; pointer: string }> {
    const rel = toRelative(options.root, resolveForRead(options.root, path));
    const key = `src-${createHash("sha256").update(rel).digest("hex").slice(0, 40)}`;
    const result = await guarded(() =>
        options.sources.mutate(
            options.workspaceId,
            {
                schema_version: "1",
                idempotency_key: key,
                operation: "register",
                target: { location: "workspace", kind: "file", path: rel },
            },
            signal,
        ),
    );
    const pointer = result.items[0]?.pointer;
    if (!pointer) throw new Error("SERVICE_UNAVAILABLE: the file could not be registered");
    return { rel, pointer };
}

function signalFor(options: SourceToolOptions, signal: AbortSignal | undefined): AbortSignal {
    const timeout = AbortSignal.timeout(options.timeoutMs);
    return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

function readView(rel: string, result: PointerReadResult): string {
    return JSON.stringify({
        path: rel,
        pointer: result.pointer,
        content: result.content,
        range: result.provenance.selection?.range ?? null,
        truncated: result.truncated,
        next_cursor: result.next_cursor ?? null,
    });
}

export function sourceTools(options: SourceToolOptions): ProjectTool[] {
    const read: ProjectTool = {
        requiresApproval: false,
        review: (value) => review("other", `read ${field(value, "path", true)}`, ""),
        refuse: () => null,
        tool: {
            name: "read_file",
            description:
                "Read part of a text file inside the workspace (at most 16 KiB per call). Optional start_line/end_line " +
                "pick lines; omit cursor on the first call and pass next_cursor back only to continue. Returns the exact range read.",
            inputSchema: objectSchema(
                {
                    path: { type: "string" },
                    start_line: { type: "integer", minimum: 1 },
                    end_line: { type: "integer", minimum: 1 },
                    max_bytes: { type: "integer", minimum: 1, maximum: READ_MAX_BYTES },
                    cursor: { type: "string", minLength: 1, maxLength: 512 },
                },
                ["path"],
            ),
            execute: async (raw, context) => {
                const values = input(raw);
                const signal = signalFor(options, context.signal);
                const { rel, pointer } = await pointerFor(options, field(values, "path", true), signal);
                const start = positive(values.start_line, "start_line");
                const end = positive(values.end_line, "end_line");
                const cap = readTokenCap();
                const result = await guarded(() =>
                    options.sources.read(
                        options.workspaceId,
                        {
                            pointer,
                            ...(start === undefined
                                ? {}
                                : { selector: { type: "line", start, ...(end ? { end } : {}) } }),
                            max_bytes: positive(values.max_bytes, "max_bytes") ?? READ_MAX_BYTES,
                            ...(cap === null ? {} : { max_tokens: cap }),
                            ...(typeof values.cursor === "string" ? { cursor: values.cursor } : {}),
                        },
                        signal,
                    ),
                );
                const selection = result.provenance.selection;
                if (selection) {
                    options.recordShown({ kind: "source", pointer, selection });
                    options.recordCited({ ref: { kind: "source", pointer, selection } });
                }
                return readView(rel, result);
            },
        },
    };
    const search: ProjectTool = {
        requiresApproval: false,
        review: (value) => review("other", `search ${field(value, "path", true)}`, ""),
        refuse: () => null,
        tool: {
            name: "search_file",
            description:
                "Find a literal string in one text file inside the workspace. Returns line numbers and short snippets; " +
                "read the lines you need with read_file. For code symbols across the project use code_search.",
            inputSchema: objectSchema(
                {
                    path: { type: "string" },
                    query: { type: "string", minLength: 1, maxLength: 256 },
                    limit: { type: "integer", minimum: 1, maximum: SEARCH_LIMIT },
                },
                ["path", "query"],
            ),
            execute: async (raw, context) => {
                const values = input(raw);
                const signal = signalFor(options, context.signal);
                const { rel, pointer } = await pointerFor(options, field(values, "path", true), signal);
                const result = await guarded(() =>
                    options.sources.search(
                        options.workspaceId,
                        { pointer, query: field(values, "query", true), limit: positive(values.limit, "limit") ?? 20 },
                        signal,
                    ),
                );
                const matches = result.matches.map((match) => ({ line: match.line, content: match.content }));
                return JSON.stringify({ path: rel, matches, truncated: result.truncated });
            },
        },
    };
    return [read, search];
}
