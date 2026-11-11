/**
 * R0 code tools (3.6): code_search returns TF-IDF Symbol Bundle candidates (metadata only, no source
 * text) and code_read returns one candidate's bundle within byte and token caps, with the verified
 * file hash and lines. No other code-search technique is offered to the model.
 */
import type { AnswerCitation, ExplicitContextRef } from "@securecode/contracts";
import { ContextServiceError } from "../../context-client/contextServiceError.js";
import type { SymbolService } from "../../context-client/workspaceServices.js";
import { recordStaleCodeRead, STALE_CODE_READ_GUIDANCE } from "../adapter/staleCodeReadGuard.js";
import { readTokenCap } from "./runtimeTools.js";
import { objectSchema, review, type ProjectTool } from "./toolSupport.js";

const BUNDLE_MAX_BYTES = 16 * 1024;
const BUNDLE_MAX_TOKENS = 8000;
const SEARCH_LIMIT = 20;

export interface CodeToolOptions {
    symbols: SymbolService;
    workspaceId: string;
    timeoutMs: number;
    recordShown(ref: ExplicitContextRef): void;
    /** Reports a verified input of the current run (answer citation). */
    recordCited(citation: AnswerCitation): void;
}

function values(raw: unknown): Record<string, unknown> {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) throw new Error("tool input must be an object");
    return raw as Record<string, unknown>;
}

async function guarded<T>(
    work: () => Promise<T>,
    read?: { candidateId: string; revision: number; toolCallId: string | undefined },
): Promise<T> {
    try {
        return await work();
    } catch (error) {
        if (error instanceof ContextServiceError) {
            if (error.code === "SOURCE_CHANGED" && read) {
                recordStaleCodeRead(read.candidateId, read.revision, read.toolCallId);
                throw new Error(STALE_CODE_READ_GUIDANCE, { cause: error });
            }
            throw new Error(`${error.code}: ${error.message}`, { cause: error });
        }
        throw error;
    }
}

function signalFor(options: CodeToolOptions, signal: AbortSignal | undefined): AbortSignal {
    const timeout = AbortSignal.timeout(options.timeoutMs);
    return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export function codeTools(options: CodeToolOptions): ProjectTool[] {
    const search: ProjectTool = {
        requiresApproval: false,
        review: () => review("other", "search code", ""),
        refuse: () => null,
        tool: {
            name: "code_search",
            description:
                "Search the indexed project code by identifiers, file names or words (TF-IDF over symbols). Returns " +
                "candidates with file, symbol and lines but no code; read one with code_read.",
            inputSchema: objectSchema(
                {
                    query: { type: "string", minLength: 1, maxLength: 2000 },
                    limit: { type: "integer", minimum: 1, maximum: SEARCH_LIMIT },
                },
                ["query"],
            ),
            execute: async (raw, context) => {
                const input = values(raw);
                if (typeof input.query !== "string" || input.query.trim() === "") throw new Error("query is required");
                const limit = typeof input.limit === "number" ? Math.min(SEARCH_LIMIT, input.limit) : 8;
                const result = await guarded(() =>
                    options.symbols.search(
                        { workspace_id: options.workspaceId, query: input.query as string, page: { limit } },
                        signalFor(options, context.signal),
                    ),
                );
                if (result.no_match) return JSON.stringify({ candidates: [], hint: result.no_match.hint ?? null });
                const candidates = result.candidates.map((candidate) => ({
                    candidate_id: candidate.candidate_id,
                    index_revision: candidate.index_revision,
                    path: candidate.primary.relative_path,
                    symbol: candidate.primary.qualname,
                    kind: candidate.primary.kind,
                    lines: [candidate.primary.start_line, candidate.primary.end_line],
                    score: Math.round(candidate.score * 1000) / 1000,
                }));
                return JSON.stringify({ candidates });
            },
        },
    };
    const read: ProjectTool = {
        requiresApproval: false,
        review: () => review("other", "read code bundle", ""),
        refuse: () => null,
        tool: {
            name: "code_read",
            description:
                "Read the source of one code_search candidate (the symbol and its static references, at most 16 KiB). " +
                "Cite the returned file and lines.",
            inputSchema: objectSchema(
                {
                    candidate_id: { type: "string", pattern: "^cand_[A-Za-z0-9-]{8,64}$" },
                    index_revision: { type: "integer", minimum: 1 },
                },
                ["candidate_id", "index_revision"],
            ),
            execute: async (raw, context) => {
                const input = values(raw);
                const candidateId = String(input.candidate_id);
                const revision = Number(input.index_revision);
                const cap = readTokenCap();
                const bundle = await guarded(
                    () =>
                        options.symbols.readBundle(
                            {
                                workspace_id: options.workspaceId,
                                candidate_id: candidateId,
                                index_revision: revision,
                                max_tokens: Math.min(BUNDLE_MAX_TOKENS, cap ?? BUNDLE_MAX_TOKENS),
                                max_bytes: BUNDLE_MAX_BYTES,
                            },
                            signalFor(options, context.signal),
                        ),
                    { candidateId, revision, toolCallId: context.toolCallId },
                );
                const ref = {
                    kind: "symbol",
                    candidate_id: bundle.candidate_id,
                    index_revision: bundle.index_revision,
                } as const;
                if (bundle.fragments.length > 0) options.recordShown(ref);
                // Cite only source fragments actually returned and verified in this read. Search
                // metadata may be absent after restart, or belong to a superseded index revision.
                for (const fragment of bundle.fragments) {
                    if (fragment.location) options.recordCited({ ref, location: fragment.location });
                }
                return JSON.stringify({
                    fragments: bundle.fragments.map((fragment) => ({
                        path: fragment.provenance.relative_path,
                        lines: [fragment.start_line, fragment.end_line],
                        content: fragment.content,
                    })),
                    omitted: bundle.omissions.length,
                });
            },
        },
    };
    return [search, read];
}
