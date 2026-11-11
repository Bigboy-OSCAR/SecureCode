/**
 * App-owned PDF tools (4.9): pdf_parse, pdf_status, pdf_search and pdf_read_pages over a registered PDF
 * Source Pointer. Parse/status return job metadata only; text leaves only as one bounded page range
 * per read or as short search previews, each with its page citation. skills/pdf-pointer/SKILL.md
 * describes these exact names and shapes (checked by pdfPointerSkill.ts and its test).
 */
import { randomUUID } from "node:crypto";
import type { AnswerCitation, PdfJobStatus } from "@securecode/contracts";
import { ContextServiceError } from "../../context-client/contextServiceError.js";
import type { PdfService } from "../../context-client/pdfClient.js";
import { readTokenCap } from "./runtimeTools.js";
import { objectSchema, review, type ProjectTool } from "./toolSupport.js";

export const PDF_TOOL_NAMES = ["pdf_parse", "pdf_status", "pdf_search", "pdf_read_pages"] as const;
const READ_MAX_BYTES = 16 * 1024;
const SEARCH_LIMIT = 50;

export interface PdfToolOptions {
    service: PdfService;
    workspaceId: string;
    timeoutMs: number;
    /** Reports a page read as a verified input of the current run (answer citation). */
    recordCited(citation: AnswerCitation): void;
}

function record(input: unknown): Record<string, unknown> {
    if (typeof input !== "object" || input === null || Array.isArray(input))
        throw new Error("tool input must be an object");
    return input as Record<string, unknown>;
}

function text(input: Record<string, unknown>, name: string): string {
    const value = input[name];
    if (typeof value !== "string" || value === "") throw new Error(`tool input field "${name}" must be a string`);
    return value;
}

function integer(input: Record<string, unknown>, name: string): number | undefined {
    const value = input[name];
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

function signalFor(options: PdfToolOptions, signal: AbortSignal | undefined): AbortSignal {
    const timeout = AbortSignal.timeout(options.timeoutMs);
    return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

/** Job metadata only: never page text. */
function jobView(status: PdfJobStatus): string {
    const view: Record<string, unknown> = { job_id: status.job_id, state: status.state };
    if ("page_count" in status) view.page_count = status.page_count;
    if ("excluded_pages" in status) view.excluded_pages = status.excluded_pages;
    if ("reason" in status) view.reason = status.reason;
    return JSON.stringify(view);
}

function tool(
    name: (typeof PDF_TOOL_NAMES)[number],
    description: string,
    properties: Record<string, unknown>,
    required: string[],
    execute: (input: Record<string, unknown>, signal: AbortSignal | undefined) => Promise<string>,
): ProjectTool {
    return {
        requiresApproval: false,
        review: () => review("other", name.replace("_", " "), ""),
        refuse: () => null,
        tool: {
            name,
            description,
            inputSchema: objectSchema(properties, required),
            execute: async (input, context) => execute(record(input), context.signal),
        },
    };
}

export function pdfTools(options: PdfToolOptions): ProjectTool[] {
    const pointer = { type: "string", minLength: 1, maxLength: 512 };
    return [
        tool(
            "pdf_parse",
            "Start or reuse text extraction for a registered PDF Source pointer. Returns job_id, state and page_count; never page text.",
            { pointer },
            ["pointer"],
            async (input, signal) =>
                jobView(
                    await guarded(() =>
                        options.service.parse(
                            options.workspaceId,
                            text(input, "pointer"),
                            `tool-${randomUUID()}`,
                            signalFor(options, signal),
                        ),
                    ),
                ),
        ),
        tool(
            "pdf_status",
            "Check a PDF parse job. Read pages only when state is ready or partial.",
            { job_id: { type: "string", pattern: "^pdf_[A-Za-z0-9-]{8,64}$" } },
            ["job_id"],
            async (input, signal) =>
                jobView(
                    await guarded(() =>
                        options.service.status(options.workspaceId, text(input, "job_id"), signalFor(options, signal)),
                    ),
                ),
        ),
        tool(
            "pdf_search",
            "Find a literal string in a parsed PDF. Returns page numbers, line numbers and short previews.",
            {
                pointer,
                query: { type: "string", minLength: 1, maxLength: 256 },
                limit: { type: "integer", minimum: 1, maximum: SEARCH_LIMIT },
            },
            ["pointer", "query"],
            async (input, signal) => {
                const result = await guarded(() =>
                    options.service.search(
                        options.workspaceId,
                        {
                            pointer: text(input, "pointer"),
                            query: text(input, "query"),
                            limit: integer(input, "limit") ?? 20,
                        },
                        signalFor(options, signal),
                    ),
                );
                const matches = result.matches.map((match) => ({
                    page: match.selection?.range.type === "pdf_page" ? match.selection.range.page : null,
                    line: match.line,
                    content: match.content,
                }));
                return JSON.stringify({ matches, truncated: result.truncated });
            },
        ),
        tool(
            "pdf_read_pages",
            "Read one page range of a parsed PDF (one page per call, at most 16 KiB). Omit cursor on the first call; pass next_cursor back as cursor only to continue. Cite the returned page.",
            {
                pointer,
                start_page: { type: "integer", minimum: 1 },
                end_page: { type: "integer", minimum: 1 },
                max_bytes: { type: "integer", minimum: 1, maximum: READ_MAX_BYTES },
                cursor: { type: "string", minLength: 1, maxLength: 512 },
            },
            ["pointer", "start_page"],
            async (input, signal) => {
                const cap = readTokenCap();
                const startPage = integer(input, "start_page") ?? 1;
                const result = await guarded(() =>
                    options.service.readPages(
                        options.workspaceId,
                        {
                            pointer: text(input, "pointer"),
                            startPage,
                            endPage: integer(input, "end_page"),
                            maxBytes: integer(input, "max_bytes"),
                            maxTokens: cap ?? undefined,
                            cursor: typeof input.cursor === "string" ? input.cursor : undefined,
                        },
                        signalFor(options, signal),
                    ),
                );
                const selection = result.provenance.selection;
                const range = selection?.range;
                if (selection) options.recordCited({ ref: { kind: "source", pointer: result.pointer, selection } });
                return JSON.stringify({
                    page: range?.type === "pdf_page" ? range.page : startPage,
                    content: result.content,
                    range: range ?? null,
                    truncated: result.truncated,
                    next_cursor: result.next_cursor ?? null,
                });
            },
        ),
    ];
}
