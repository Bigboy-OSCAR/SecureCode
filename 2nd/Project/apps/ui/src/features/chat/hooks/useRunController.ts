import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import type { SessionId, WorkspaceId } from "@securecode/contracts";
import type { RunClient } from "../../../api/runClient.js";
import { RunController } from "../model/runController.js";

export function useRunController(
    client: RunClient,
    sessionId: SessionId,
    workspaceId: WorkspaceId,
    now: () => number = Date.now,
): { controller: RunController; state: ReturnType<RunController["getSnapshot"]> } {
    const controller = useMemo(
        () => new RunController(client, sessionId, workspaceId, undefined, now),
        [client, sessionId, workspaceId, now],
    );
    const disposalTokens = useRef(new WeakMap<RunController, number>());
    const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);

    useEffect(() => {
        const token = (disposalTokens.current.get(controller) ?? 0) + 1;
        disposalTokens.current.set(controller, token);
        return () => {
            queueMicrotask(() => {
                if (disposalTokens.current.get(controller) === token) {
                    controller.dispose();
                    disposalTokens.current.delete(controller);
                }
            });
        };
    }, [controller]);

    return { controller, state };
}
