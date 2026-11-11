/** Persist only selection IDs in the native launcher when its web view uses an ephemeral origin. */
export function persistNativeSelection(workspaceId: string, sessionId?: string): void {
    const desktop = globalThis as typeof globalThis & {
        webkit?: {
            messageHandlers?: {
                saveSelection?: { postMessage: (value: { workspaceId: string; sessionId?: string }) => void };
            };
        };
    };
    desktop.webkit?.messageHandlers?.saveSelection?.postMessage({ workspaceId, ...(sessionId ? { sessionId } : {}) });
}
