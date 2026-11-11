/**
 * Persisted run state and its RunSnapshot view. The record keeps everything
 * the snapshot needs (answer, bounded tool summaries, approvals, terminal);
 * replay positions come from the in-memory event log.
 */
import type {
    AnswerCitation,
    ApprovalOutcome,
    ApprovalRequest,
    ReplayWindow,
    RunSnapshot,
    RunStatus,
    RunSummary,
    RunTerminal,
    ToolCallSummary,
} from "@securecode/contracts";
import { paginate, type PageRequestInput } from "../shared/pagination.js";

export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set(["completed", "failed", "cancelled"]);
export const ANSWER_MAX_CHARS = 65536;
export const TOOL_CALLS_MAX = 50;
export const PENDING_APPROVALS_MAX = 8;
export const CITATIONS_MAX = 200;
const HISTORY_PAGE_SIZE = 50;

export interface RunRecord {
    run_id: string;
    session_id: string;
    workspace_id: string;
    status: RunStatus;
    created_at: string;
    updated_at: string;
    prompt_preview: string;
    answer_text: string;
    answer_truncated: boolean;
    tool_calls: ToolCallSummary[];
    tool_calls_truncated: boolean;
    pending_approvals: ApprovalRequest[];
    approval_history: ApprovalOutcome[];
    terminal: RunTerminal | null;
    last_sequence: number;
    /** Verified inputs of this run; absent in records written before 1.6. */
    citations?: AnswerCitation[];
}

export function isTerminal(status: RunStatus): boolean {
    return TERMINAL_STATUSES.has(status);
}

export interface SnapshotQuery {
    approvalCursor?: string;
    citationCursor?: string;
}

/** A bundle may cite several symbols with the same candidate ref. */
export function citationKey(citation: AnswerCitation): string {
    return JSON.stringify({ ref: citation.ref, ...("location" in citation ? { location: citation.location } : {}) });
}

function expandedCitations(citations: AnswerCitation[]): AnswerCitation[] {
    const seen = new Set<string>();
    return citations
        .flatMap<AnswerCitation>((citation) => {
            const expanded: AnswerCitation[] =
                "related_locations" in citation
                    ? [
                          citation,
                          ...(citation.related_locations ?? []).map((location) => ({ ref: citation.ref, location })),
                      ]
                    : [citation];
            return expanded.filter((item) => {
                const key = citationKey(item);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        })
        .slice(0, CITATIONS_MAX);
}

export function toSnapshot(record: RunRecord, replay: ReplayWindow, query: SnapshotQuery = {}): RunSnapshot {
    const scope = `approvals:${record.run_id}:${record.last_sequence}`;
    const request: PageRequestInput = { limit: HISTORY_PAGE_SIZE };
    if (query.approvalCursor) request.cursor = query.approvalCursor;
    const history = paginate(record.approval_history, scope, request);
    const citationRequest: PageRequestInput = { limit: HISTORY_PAGE_SIZE };
    if (query.citationCursor) citationRequest.cursor = query.citationCursor;
    const cited = expandedCitations(record.citations ?? []);
    const citations = paginate(cited, `citations:${record.run_id}:${cited.length}`, citationRequest);
    return {
        schema_version: "1",
        run_id: record.run_id,
        session_id: record.session_id,
        workspace_id: record.workspace_id,
        status: record.status,
        created_at: record.created_at,
        updated_at: record.updated_at,
        prompt_preview: record.prompt_preview,
        replay,
        answer: {
            text: record.answer_text,
            truncated: record.answer_truncated,
            citations: citations.items,
            citations_page: citations.page,
        },
        tool_calls: record.tool_calls,
        ...(record.tool_calls_truncated ? { tool_calls_truncated: true } : {}),
        pending_approvals: record.pending_approvals,
        terminal: record.terminal,
        approval_history: history.items,
        approval_history_page: history.page,
    };
}

export function toSummary(record: RunRecord): RunSummary {
    return {
        run_id: record.run_id,
        status: record.status,
        created_at: record.created_at,
        prompt_preview: record.prompt_preview,
    };
}
