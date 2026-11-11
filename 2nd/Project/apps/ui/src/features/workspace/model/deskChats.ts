/** Load every conversation and its title, following all server pagination cursors. */
import type { RunSummary, Session, Workspace } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";

export interface DeskChat {
    session: Session;
    runs: RunSummary[];
    title: string;
}

export async function readChats(api: ApiHttpClient, workspace: Workspace): Promise<DeskChat[]> {
    const sessions: Session[] = [];
    let cursor: string | undefined;
    do {
        const page = await api.listSessions(workspace.workspace_id, cursor);
        sessions.push(...page.items);
        cursor = page.page.next_cursor ?? undefined;
    } while (cursor);
    return Promise.all(
        sessions.map(async (session) => {
            const runs: RunSummary[] = [];
            let runCursor: string | undefined;
            do {
                const page = await api.listRuns(session.session_id, runCursor);
                runs.push(...page.items);
                runCursor = page.page.next_cursor ?? undefined;
            } while (runCursor);
            runs.sort((a, b) => a.created_at.localeCompare(b.created_at));
            return { session, runs, title: runs[0]?.prompt_preview ?? "새 대화" };
        }),
    );
}
