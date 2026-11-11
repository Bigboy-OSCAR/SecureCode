import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionId, SourceMutationRequest, WorkspaceId } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { mapPointerItem, type UiPointer } from "../../../api/mappers/pointerMapper.js";
import { createIdempotencyKey } from "../../../api/runClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import {
    createListQuery,
    emptyPage,
    mergePointers,
    replacePointer,
    toPointerPage,
    type PointerPage,
} from "../model/pointerCatalogHelpers.js";

export function useLivePointerCatalog(
    api: ApiHttpClient,
    workspaceId: WorkspaceId | null,
    sessionId: SessionId | null,
): {
    sourcePage: PointerPage;
    runtimePage: PointerPage;
    selectedPointer: UiPointer | null;
    busy: string | null;
    error: string | null;
    notice: string | null;
    selectPointer: (pointer: UiPointer | null) => void;
    registerExternalFile: (path: string) => Promise<void>;
    refreshSource: (pointer: UiPointer) => Promise<void>;
    removePointer: (pointer: UiPointer) => Promise<void>;
    loadMore: (kind: "source" | "runtime") => Promise<void>;
    refreshRuntime: () => Promise<void>;
} {
    const [sourcePage, setSourcePage] = useState<PointerPage>(emptyPage);
    const [runtimePage, setRuntimePage] = useState<PointerPage>(emptyPage);
    const [selectedPointer, setSelectedPointer] = useState<UiPointer | null>(null);
    const [busy, setBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const generation = useRef(0);

    useEffect(() => {
        const requestGeneration = ++generation.current;
        setSourcePage(emptyPage());
        setRuntimePage(emptyPage());
        setSelectedPointer(null);
        setError(null);
        setNotice(null);

        if (!workspaceId) {
            return () => {
                generation.current += 1;
            };
        }

        const load = async (kind: "source" | "runtime"): Promise<void> => {
            const query = createListQuery(kind, sessionId);
            if (!query) {
                return;
            }
            try {
                const page = await api.listPointers(workspaceId, query);
                if (requestGeneration !== generation.current) {
                    return;
                }
                const next = toPointerPage(page.items.map(mapPointerItem), page.page);
                if (kind === "source") {
                    setSourcePage(next);
                } else {
                    setRuntimePage(next);
                }
            } catch (requestError) {
                if (requestGeneration === generation.current) {
                    setError(
                        formatApiFailure(
                            requestError,
                            `${kind === "source" ? "등록 자료" : "실행 결과"}를 불러오지 못했습니다.`,
                        ),
                    );
                }
            }
        };

        void load("source");
        if (sessionId) {
            void load("runtime");
        }
        return () => {
            generation.current += 1;
        };
    }, [api, workspaceId, sessionId]);

    const registerExternalFile = async (path: string): Promise<void> => {
        if (!workspaceId) {
            setError("먼저 프로젝트를 등록하세요.");
            return;
        }
        setBusy("register");
        setError(null);
        setNotice(null);
        try {
            const request: SourceMutationRequest = {
                schema_version: "1",
                idempotency_key: createIdempotencyKey(),
                operation: "register",
                target: { location: "external", kind: "file", path },
            };
            const result = await api.registerSource(workspaceId, request);
            const added = result.items.map(mapPointerItem);
            setSourcePage((current) => ({ ...current, items: mergePointers(current.items, added) }));
            setSelectedPointer(added[0] ?? null);
            if (result.status === "partial" || result.issues.length > 0) {
                setNotice(`일부 자료를 등록하지 못했습니다 (${result.issues.length}개). 등록 결과를 확인하세요.`);
            } else {
                setNotice("지정한 외부 파일을 Source Pointer로 등록했습니다. 브라우저는 파일 내용을 읽지 않았습니다.");
            }
        } catch (requestError) {
            setError(formatApiFailure(requestError, "지정한 파일을 등록하지 못했습니다."));
        } finally {
            setBusy(null);
        }
    };

    const refreshSource = async (pointer: UiPointer): Promise<void> => {
        if (!workspaceId || pointer.kind !== "source") {
            return;
        }
        setBusy("refresh");
        setError(null);
        setNotice(null);
        try {
            const request: SourceMutationRequest = {
                schema_version: "1",
                idempotency_key: createIdempotencyKey(),
                operation: "refresh",
                pointer: pointer.pointer,
            };
            const result = await api.registerSource(workspaceId, request);
            const refreshed = result.items.map(mapPointerItem);
            setSourcePage((current) => ({
                ...current,
                items: replacePointer(current.items, pointer.pointer, refreshed),
            }));
            setSelectedPointer(refreshed[0] ?? null);
            setNotice("원본을 다시 확인하고 Source 등록 정보를 갱신했습니다.");
        } catch (requestError) {
            setError(formatApiFailure(requestError, "Source 등록을 갱신하지 못했습니다."));
        } finally {
            setBusy(null);
        }
    };

    const removePointer = async (pointer: UiPointer): Promise<void> => {
        if (!workspaceId) {
            return;
        }
        const requestGeneration = ++generation.current;
        setBusy("delete");
        setError(null);
        setNotice(null);
        setSelectedPointer((current) => (current?.pointer === pointer.pointer ? null : current));
        try {
            await api.deletePointer(
                pointer.kind === "source"
                    ? {
                          schema_version: "1",
                          idempotency_key: createIdempotencyKey(),
                          kind: "source",
                          pointer: pointer.pointer,
                          workspace_id: workspaceId,
                      }
                    : {
                          schema_version: "1",
                          idempotency_key: createIdempotencyKey(),
                          kind: "runtime",
                          pointer: pointer.pointer,
                          workspace_id: workspaceId,
                          session_id: pointer.session_id,
                      },
            );
            setSourcePage((current) => ({
                ...current,
                items: current.items.filter((item) => item.pointer !== pointer.pointer),
            }));
            setRuntimePage((current) => ({
                ...current,
                items: current.items.filter((item) => item.pointer !== pointer.pointer),
            }));
            setNotice(
                pointer.kind === "source"
                    ? "Source 등록을 해제했습니다. 원본 파일은 삭제하지 않았습니다."
                    : "선택한 Runtime Pointer를 삭제했습니다. 이미 실행된 도구는 되돌리지 않습니다.",
            );
        } catch (requestError) {
            setError(formatApiFailure(requestError, "포인터를 삭제하지 못했습니다."));
        } finally {
            if (requestGeneration === generation.current) {
                setBusy(null);
            }
        }
    };

    const loadMore = async (kind: "source" | "runtime"): Promise<void> => {
        if (!workspaceId) {
            return;
        }
        const current = kind === "source" ? sourcePage : runtimePage;
        if (!current.nextCursor) {
            return;
        }
        const query = createListQuery(kind, sessionId, current.nextCursor);
        if (!query) return;
        const requestGeneration = generation.current;
        setBusy(`more-${kind}`);
        setError(null);
        try {
            const page = await api.listPointers(workspaceId, query);
            if (requestGeneration !== generation.current) {
                return;
            }
            const items = page.items.map(mapPointerItem);
            const updatePage = (previous: PointerPage): PointerPage => ({
                ...toPointerPage(mergePointers(previous.items, items), page.page),
            });
            if (kind === "source") {
                setSourcePage(updatePage);
            } else {
                setRuntimePage(updatePage);
            }
        } catch (requestError) {
            if (requestGeneration === generation.current) {
                setError(formatApiFailure(requestError, "포인터 목록의 다음 페이지를 불러오지 못했습니다."));
            }
        } finally {
            if (requestGeneration === generation.current) {
                setBusy(null);
            }
        }
    };

    const refreshRuntime = useCallback(async (): Promise<void> => {
        if (!workspaceId || !sessionId) {
            return;
        }
        const requestGeneration = generation.current;
        setBusy("runtime-refresh");
        setError(null);
        try {
            const page = await api.listPointers(workspaceId, { kind: "runtime", session_id: sessionId, limit: 100 });
            if (requestGeneration !== generation.current) {
                return;
            }
            const items = page.items.map(mapPointerItem);
            setRuntimePage(toPointerPage(items, page.page));
            setSelectedPointer((current) => {
                if (current?.kind !== "runtime") {
                    return current;
                }
                return items.find((item) => item.pointer === current.pointer) ?? null;
            });
        } catch (requestError) {
            if (requestGeneration === generation.current) {
                setError(formatApiFailure(requestError, "현재 세션의 Runtime Pointer 목록을 갱신하지 못했습니다."));
            }
        } finally {
            if (requestGeneration === generation.current) {
                setBusy(null);
            }
        }
    }, [api, sessionId, workspaceId]);

    return {
        sourcePage,
        runtimePage,
        selectedPointer,
        busy,
        error,
        notice,
        selectPointer: setSelectedPointer,
        registerExternalFile,
        refreshSource,
        removePointer,
        loadMore,
        refreshRuntime,
    };
}
