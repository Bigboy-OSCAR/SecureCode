/**
 * Persisted run state and its RunSnapshot view. The record keeps everything
 * the snapshot needs (answer, bounded tool summaries, approvals, terminal);
 * replay positions come from the in-memory event log.
 */
import type {
    ApprovalOutcome,
    ApprovalRequest,
    PageInfo,
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
}

export function isTerminal(status: RunStatus): boolean {
    return TERMINAL_STATUSES.has(status);
}

const EMPTY_PAGE: PageInfo = { limit: HISTORY_PAGE_SIZE, next_cursor: null, has_more: false };

export interface SnapshotQuery {
    approvalCursor?: string;
    citationCursor?: string;
}

export function toSnapshot(record: RunRecord, replay: ReplayWindow, query: SnapshotQuery = {}): RunSnapshot {
    const scope = `approvals:${record.run_id}:${record.last_sequence}`;
    const request: PageRequestInput = { limit: HISTORY_PAGE_SIZE };
    if (query.approvalCursor) request.cursor = query.approvalCursor;
    const history = paginate(record.approval_history, scope, request);
    if (query.citationCursor) {
        // Citations arrive with 3.6; no citation cursor has been issued yet.
        paginate([], `citations:${record.run_id}`, { cursor: query.citationCursor });
    }
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
            citations: [],
            citations_page: EMPTY_PAGE,
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
