import { useEffect } from "react";
import { useLivePointerCatalog } from "../hooks/useLivePointerCatalog.js";
import { LivePointerPanel } from "./LivePointerPanel.js";
import { LivePointerReadPanel } from "./LivePointerReadPanel.js";
import { LivePdfPanel } from "./LivePdfPanel.js";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import type { PointerSelection, SessionId, WorkspaceId } from "@securecode/contracts";
import type { UiPointer } from "../../../api/mappers/pointerMapper.js";

interface LivePointerWorkspaceProps {
    api: ApiHttpClient;
    connected: boolean;
    workspaceId: WorkspaceId | null;
    sessionId: SessionId | null;
    runtimePointerRuns: Readonly<Record<string, string>>;
    onReadSelection: (pointer: UiPointer | null, selection: PointerSelection | null) => void;
}

export function LivePointerWorkspace({
    api,
    connected,
    workspaceId,
    sessionId,
    runtimePointerRuns,
    onReadSelection,
}: LivePointerWorkspaceProps): React.JSX.Element {
    const catalog = useLivePointerCatalog(api, workspaceId, sessionId);

    useEffect(() => {
        if (Object.keys(runtimePointerRuns).length > 0) {
            void catalog.refreshRuntime();
        }
    }, [catalog.refreshRuntime, runtimePointerRuns]);

    return (
        <>
            <LivePointerPanel
                workspaceId={workspaceId}
                sessionId={sessionId}
                runtimePointerRuns={runtimePointerRuns}
                canMutate={connected}
                catalog={catalog}
            />
            <LivePointerReadPanel
                api={api}
                pointer={catalog.selectedPointer}
                canRead={connected}
                onSelectionChange={onReadSelection}
            />
            <LivePdfPanel api={api} pointer={catalog.selectedPointer} canMutate={connected} />
        </>
    );
}
