import { useCallback, useEffect, useState } from "react";
import type { IndexStatusResponse, WorkspaceId } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { createIdempotencyKey } from "../../../api/runClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";

const pollingIntervalMs = 750;

export function useIndexWorkflow(
    api: ApiHttpClient,
    workspaceId: WorkspaceId | null,
): {
    status: IndexStatusResponse | null;
    error: string | null;
    busy: boolean;
    start: () => Promise<void>;
    refresh: () => Promise<void>;
} {
    const [status, setStatus] = useState<IndexStatusResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [pollVersion, setPollVersion] = useState(0);

    useEffect(() => {
        let active = true;
        let timer: ReturnType<typeof setTimeout> | undefined;
        setStatus(null);
        setError(null);

        if (!workspaceId) {
            return () => {
                active = false;
            };
        }

        const poll = async (): Promise<void> => {
            try {
                const next = await api.getIndexStatus(workspaceId);
                if (!active) {
                    return;
                }
                setStatus(next);
                setError(null);
                if (next.index_status === "queued" || next.index_status === "indexing") {
                    timer = setTimeout(() => void poll(), pollingIntervalMs);
                }
            } catch (requestError) {
                if (active) {
                    setError(formatApiFailure(requestError, "색인 상태를 불러오지 못했습니다."));
                }
            }
        };

        void poll();
        return () => {
            active = false;
            if (timer) {
                clearTimeout(timer);
            }
        };
    }, [api, workspaceId, pollVersion]);

    const start = async (): Promise<void> => {
        if (!workspaceId || busy) {
            return;
        }
        setBusy(true);
        setError(null);
        try {
            const queued = await api.startIndex(workspaceId, { idempotency_key: createIdempotencyKey() });
            setStatus(queued);
            setPollVersion((version) => version + 1);
        } catch (requestError) {
            setError(formatApiFailure(requestError, "색인 생성을 시작하지 못했습니다."));
        } finally {
            setBusy(false);
        }
    };

    /** Re-reads the status without clearing it, so a revision-keyed screen keeps its current result. */
    const refresh = useCallback(async (): Promise<void> => {
        if (!workspaceId) {
            return;
        }
        try {
            const next = await api.getIndexStatus(workspaceId);
            setStatus((current) => (current && current.workspace_id !== next.workspace_id ? current : next));
        } catch (requestError) {
            setError(formatApiFailure(requestError, "색인 상태를 불러오지 못했습니다."));
        }
    }, [api, workspaceId]);

    return { status, error, busy, start, refresh };
}
