import { useEffect, useRef, useState } from "react";
import type { PdfJobStatus } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { createIdempotencyKey } from "../../../api/runClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import type { UiPointer } from "../../../api/mappers/pointerMapper.js";

const pollingIntervalMs = 700;

export function useLivePdfWorkflow(
    api: ApiHttpClient,
    pointer: UiPointer | null,
): {
    job: PdfJobStatus | null;
    busy: boolean;
    error: string | null;
    parse: () => Promise<void>;
} {
    const [job, setJob] = useState<PdfJobStatus | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const generation = useRef(0);

    useEffect(() => {
        generation.current += 1;
        setJob(null);
        setError(null);
        setBusy(false);
        return () => {
            generation.current += 1;
        };
    }, [pointer?.pointer, pointer?.revision]);

    const parse = async (): Promise<void> => {
        if (!pointer || pointer.kind !== "source") {
            return;
        }
        const requestGeneration = ++generation.current;
        setBusy(true);
        setError(null);
        setJob(null);
        try {
            let current = await api.parsePdf({
                schema_version: "1",
                workspace_id: pointer.workspace_id,
                pointer: pointer.pointer,
                idempotency_key: createIdempotencyKey(),
            });
            if (requestGeneration !== generation.current) {
                return;
            }
            setJob(current);
            while (current.state === "queued" || current.state === "running") {
                await delay(pollingIntervalMs);
                if (requestGeneration !== generation.current) {
                    return;
                }
                current = await api.getPdfJob(current.job_id);
                if (requestGeneration === generation.current) {
                    setJob(current);
                }
            }
        } catch (requestError) {
            if (requestGeneration === generation.current) {
                setError(formatApiFailure(requestError, "PDF 처리 상태를 확인하지 못했습니다."));
            }
        } finally {
            if (requestGeneration === generation.current) {
                setBusy(false);
            }
        }
    };

    return { job, busy, error, parse };
}

function delay(milliseconds: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
