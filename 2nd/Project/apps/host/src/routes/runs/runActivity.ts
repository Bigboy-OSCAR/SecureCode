/** Match both pre-record planning and persisted active runs without affecting unrelated sessions. */
import type { SessionStore } from "../sessions/sessionStore.js";
import type { RunRecorder } from "./runRecorder.js";

export function hasActiveWork(
    planning: ReadonlySet<string>,
    recorders: Iterable<RunRecorder>,
    sessions: SessionStore,
    workspaceId?: string,
    sessionId?: string,
): boolean {
    for (const id of planning)
        if ((!sessionId || id === sessionId) && (!workspaceId || sessions.get(id).workspace_id === workspaceId))
            return true;
    return [...recorders].some(
        (recorder) =>
            !recorder.terminal &&
            (!workspaceId || recorder.record.workspace_id === workspaceId) &&
            (!sessionId || recorder.record.session_id === sessionId),
    );
}
