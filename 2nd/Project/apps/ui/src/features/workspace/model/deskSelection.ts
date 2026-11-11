/** Only navigation IDs are saved locally; conversation data remains server-owned. */
export const SELECTION_KEY = "localdesk.selection.v1";

export function readSelection(): { workspaceId?: string; sessionId?: string } {
    try {
        const data: unknown = JSON.parse(localStorage.getItem(SELECTION_KEY) ?? "{}");
        if (typeof data !== "object" || !data) return {};
        return {
            workspaceId: "workspaceId" in data && typeof data.workspaceId === "string" ? data.workspaceId : undefined,
            sessionId: "sessionId" in data && typeof data.sessionId === "string" ? data.sessionId : undefined,
        };
    } catch {
        return {};
    }
}
