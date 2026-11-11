/** Model inventory and switch state come from the local host. */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ModelListResponse } from "@securecode/contracts";
import { ModelClient } from "../../../api/modelClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
export interface DeskModelState {
    models: ModelListResponse | null;
    loading: string | null;
    error: string | null;
    notice: string | null;
    refresh: () => Promise<void>;
    select: (id: string) => Promise<void>;
}
export function useDeskModels(connected: boolean): DeskModelState {
    const client = useMemo(() => new ModelClient(), []);
    const [models, setModels] = useState<ModelListResponse | null>(null);
    const [loading, setLoading] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const refresh = useCallback(async (): Promise<void> => {
        if (!connected) return;
        try {
            setModels(await client.list());
            setError(null);
        } catch (failure) {
            setError(formatApiFailure(failure, "설치된 모델을 확인하지 못했습니다."));
        }
    }, [client, connected]);
    useEffect(() => {
        void refresh();
    }, [refresh]);
    useEffect(() => {
        if (models?.status !== "loading") return;
        const timer = setTimeout(() => void refresh(), 1000);
        return () => clearTimeout(timer);
    }, [models, refresh]);
    const select = async (id: string): Promise<void> => {
        if (loading) return;
        setLoading(id);
        setError(null);
        setNotice(null);
        try {
            const next = await client.select(id);
            setModels(next);
            setNotice("모델이 변경되었습니다. 대화 기록은 유지되며 새 모델로 다음 질문을 시작합니다.");
        } catch (failure) {
            await refresh();
            setError(formatApiFailure(failure, "모델을 불러오지 못했습니다."));
        } finally {
            setLoading(null);
        }
    };
    return { models, loading, error, notice, refresh, select };
}
