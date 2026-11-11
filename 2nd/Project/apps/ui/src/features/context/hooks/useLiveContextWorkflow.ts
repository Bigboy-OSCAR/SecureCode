import { useEffect, useRef, useState } from "react";
import type {
    ContextPreviewPlan,
    IndexStatusResponse,
    SessionId,
    SelectedPointerContextRef,
    SymbolBundle,
    SymbolSearchResponse,
    WorkspaceId,
} from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { ApiClientError, formatApiFailure } from "../../../api/apiErrors.js";

export function useLiveContextWorkflow(
    api: ApiHttpClient,
    workspaceId: WorkspaceId | null,
    sessionId: SessionId | null,
    index: IndexStatusResponse | null,
    pointerContextRef: SelectedPointerContextRef | null,
): {
    query: string;
    prompt: string;
    search: SymbolSearchResponse | null;
    bundle: SymbolBundle | null;
    plan: ContextPreviewPlan | null;
    selectedCandidateId: string | null;
    busy: "search" | "bundle" | "plan" | null;
    error: string | null;
    errorCode: string | null;
    searchCursor: string | null;
    setQuery: (value: string) => void;
    setPrompt: (value: string) => void;
    selectCandidate: (candidateId: string) => void;
    searchSymbols: () => Promise<void>;
    searchNext: () => Promise<void>;
    readBundle: () => Promise<void>;
    previewPlan: () => Promise<void>;
} {
    const [query, setQuery] = useState("");
    const [prompt, setPrompt] = useState("");
    const [search, setSearch] = useState<SymbolSearchResponse | null>(null);
    const [bundle, setBundle] = useState<SymbolBundle | null>(null);
    const [plan, setPlan] = useState<ContextPreviewPlan | null>(null);
    const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
    const [busy, setBusy] = useState<"search" | "bundle" | "plan" | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [errorCode, setErrorCode] = useState<string | null>(null);
    const [searchCursor, setSearchCursor] = useState<string | null>(null);
    const requestSequence = useRef(0);
    const indexRevision = index?.index_revision ?? null;
    const pointerContextKey = pointerContextRef ? JSON.stringify(pointerContextRef) : "";

    useEffect(() => {
        requestSequence.current += 1;
        setSearch(null);
        setBundle(null);
        setPlan(null);
        setSelectedCandidateId(null);
        setSearchCursor(null);
        setError(null);
        setErrorCode(null);
        setBusy(null);
        return () => {
            requestSequence.current += 1;
        };
    }, [workspaceId, sessionId, indexRevision, pointerContextKey]);

    const searchSymbols = async (): Promise<void> => {
        if (!workspaceId || !indexRevision || !index?.searchable || index.index_status === "stale") {
            setError("최신 검색 가능한 R0 색인을 먼저 생성하세요.");
            setErrorCode(null);
            return;
        }
        if (!query.trim()) {
            setError("검색어를 입력하세요.");
            setErrorCode(null);
            return;
        }
        const sequence = ++requestSequence.current;
        setBusy("search");
        setError(null);
        setErrorCode(null);
        setSearch(null);
        setSearchCursor(null);
        setBundle(null);
        setPlan(null);
        try {
            const response = await api.previewContext({
                operation: "search",
                input: { workspace_id: workspaceId, query: query.trim(), index_revision: indexRevision },
            });
            if (sequence !== requestSequence.current) {
                return;
            }
            if (response.operation !== "search") {
                throw new Error("검색 응답 작업 유형이 일치하지 않습니다.");
            }
            setSearch(response.result);
            setSelectedCandidateId(response.result.candidates[0]?.candidate_id ?? null);
            setSearchCursor(response.result.page.next_cursor);
        } catch (requestError) {
            if (sequence === requestSequence.current) {
                setError(formatApiFailure(requestError, "R0 심볼 검색에 실패했습니다."));
                setErrorCode(requestError instanceof ApiClientError ? (requestError.code ?? null) : null);
            }
        } finally {
            if (sequence === requestSequence.current) {
                setBusy(null);
            }
        }
    };

    const searchNext = async (): Promise<void> => {
        if (!workspaceId || !indexRevision || !searchCursor || !index?.searchable) {
            return;
        }
        const sequence = ++requestSequence.current;
        setBusy("search");
        setError(null);
        setErrorCode(null);
        try {
            const response = await api.previewContext({
                operation: "search",
                input: {
                    workspace_id: workspaceId,
                    query: query.trim(),
                    index_revision: indexRevision,
                    page: { limit: 20, cursor: searchCursor },
                },
            });
            if (sequence !== requestSequence.current) {
                return;
            }
            if (response.operation !== "search") {
                throw new Error("검색 응답 작업 유형이 일치하지 않습니다.");
            }
            setSearch((current) =>
                current
                    ? { ...response.result, candidates: [...current.candidates, ...response.result.candidates] }
                    : response.result,
            );
            setSearchCursor(response.result.page.next_cursor);
        } catch (requestError) {
            if (sequence === requestSequence.current) {
                setError(formatApiFailure(requestError, "R0 검색의 다음 페이지를 불러오지 못했습니다."));
                setErrorCode(requestError instanceof ApiClientError ? (requestError.code ?? null) : null);
            }
        } finally {
            if (sequence === requestSequence.current) {
                setBusy(null);
            }
        }
    };

    const readBundle = async (): Promise<void> => {
        if (!workspaceId || !indexRevision || !selectedCandidateId) {
            setError("원문 묶음을 확인할 심볼 후보를 선택하세요.");
            setErrorCode(null);
            return;
        }
        const sequence = ++requestSequence.current;
        setBusy("bundle");
        setError(null);
        setErrorCode(null);
        setBundle(null);
        try {
            const response = await api.previewContext({
                operation: "bundle",
                input: {
                    workspace_id: workspaceId,
                    candidate_id: selectedCandidateId,
                    index_revision: indexRevision,
                    max_tokens: 2000,
                    max_bytes: 8192,
                },
            });
            if (sequence !== requestSequence.current) {
                return;
            }
            if (response.operation !== "bundle") {
                throw new Error("원문 묶음 응답 작업 유형이 일치하지 않습니다.");
            }
            setBundle(response.result);
        } catch (requestError) {
            if (sequence === requestSequence.current) {
                setError(formatApiFailure(requestError, "R0 원문 묶음을 불러오지 못했습니다."));
                setErrorCode(requestError instanceof ApiClientError ? (requestError.code ?? null) : null);
            }
        } finally {
            if (sequence === requestSequence.current) {
                setBusy(null);
            }
        }
    };

    const previewPlan = async (): Promise<void> => {
        if (!workspaceId || !sessionId || !indexRevision || !index?.searchable || index.index_status === "stale") {
            setError("세션과 최신 검색 가능한 색인이 필요합니다.");
            setErrorCode(null);
            return;
        }
        if (!prompt.trim()) {
            setError("컨텍스트를 확인할 실제 질문을 입력하세요.");
            setErrorCode(null);
            return;
        }
        const sequence = ++requestSequence.current;
        setBusy("plan");
        setError(null);
        setErrorCode(null);
        setPlan(null);
        try {
            const response = await api.previewContext({
                operation: "plan",
                input: {
                    workspace_id: workspaceId,
                    session_id: sessionId,
                    index_revision: indexRevision,
                    prompt: prompt.trim(),
                    context_refs: pointerContextRef ? [pointerContextRef] : [],
                },
            });
            if (sequence !== requestSequence.current) {
                return;
            }
            if (response.operation !== "plan") {
                throw new Error("컨텍스트 계획 응답 작업 유형이 일치하지 않습니다.");
            }
            setPlan(response.result);
        } catch (requestError) {
            if (sequence === requestSequence.current) {
                setError(formatApiFailure(requestError, "컨텍스트 예산 미리보기에 실패했습니다."));
                setErrorCode(requestError instanceof ApiClientError ? (requestError.code ?? null) : null);
            }
        } finally {
            if (sequence === requestSequence.current) {
                setBusy(null);
            }
        }
    };

    return {
        query,
        prompt,
        search,
        bundle,
        plan,
        selectedCandidateId,
        busy,
        error,
        errorCode,
        searchCursor,
        setQuery,
        setPrompt,
        selectCandidate: (candidateId) => {
            setSelectedCandidateId(candidateId);
            setBundle(null);
        },
        searchSymbols,
        searchNext,
        readBundle,
        previewPlan,
    };
}
