import { useEffect, useRef, useState } from "react";
import type { PointerReadResult, PointerSearchResult } from "@securecode/contracts";
import { ApiClientError, formatApiFailure } from "../../../api/apiErrors.js";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import type { UiPointer } from "../../../api/mappers/pointerMapper.js";
import { buildSelector, rangeProblem, type SelectorKind } from "../model/pointerSelector.js";

export function useLivePointerReadWorkflow(
    api: ApiHttpClient,
    pointer: UiPointer | null,
): {
    selectorKind: SelectorKind;
    start: string;
    end: string;
    selectorValue: string;
    query: string;
    read: PointerReadResult | null;
    matches: PointerSearchResult["matches"];
    nextReadCursor: string | null;
    nextSearchCursor: string | null;
    searchCompleted: boolean;
    busy: "read" | "search" | "next-read" | "next-search" | null;
    error: string | null;
    errorCode: string | null;
    errorReason: string | null;
    setSelectorKind: (value: SelectorKind) => void;
    setStart: (value: string) => void;
    setEnd: (value: string) => void;
    setSelectorValue: (value: string) => void;
    setQuery: (value: string) => void;
    readPointer: () => Promise<void>;
    readNext: () => Promise<void>;
    searchPointer: () => Promise<void>;
    searchNext: () => Promise<void>;
} {
    const [selectorKind, setSelectorKind] = useState<SelectorKind>("line");
    const [start, setStart] = useState("1");
    const [end, setEnd] = useState("");
    const [selectorValue, setSelectorValue] = useState("");
    const [query, setQuery] = useState("");
    const [read, setRead] = useState<PointerReadResult | null>(null);
    const [matches, setMatches] = useState<PointerSearchResult["matches"]>([]);
    const [searchCompleted, setSearchCompleted] = useState(false);
    const [nextReadCursor, setNextReadCursor] = useState<string | null>(null);
    const [nextSearchCursor, setNextSearchCursor] = useState<string | null>(null);
    const [busy, setBusy] = useState<"read" | "search" | "next-read" | "next-search" | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [errorCode, setErrorCode] = useState<string | null>(null);
    const [errorReason, setErrorReason] = useState<string | null>(null);
    const sequence = useRef(0);

    useEffect(() => {
        sequence.current += 1;
        setRead(null);
        setMatches([]);
        setSearchCompleted(false);
        setNextReadCursor(null);
        setNextSearchCursor(null);
        setError(null);
        setErrorCode(null);
        setErrorReason(null);
        setBusy(null);
        const supported = pointer?.supported_selectors ?? [];
        setSelectorKind(supported.includes("line") ? "line" : (supported[0] ?? "line"));
        return () => {
            sequence.current += 1;
        };
    }, [pointer?.pointer, pointer?.revision, pointer?.supported_selectors]);

    const readPointer = async (): Promise<void> => {
        if (!pointer) {
            return;
        }
        const selector = buildSelector(selectorKind, start, end, selectorValue);
        if (!selector) {
            setError(rangeProblem(selectorKind, start));
            setErrorCode(null);
            setErrorReason(null);
            return;
        }
        const requestSequence = ++sequence.current;
        setBusy("read");
        clearError();
        setRead(null);
        setNextReadCursor(null);
        try {
            const result = await api.readPointer({
                schema_version: "1",
                pointer: pointer.pointer,
                selector,
                max_bytes: 4096,
            });
            if (requestSequence === sequence.current) {
                setRead(result);
                setNextReadCursor(result.next_cursor ?? null);
            }
        } catch (requestError) {
            if (requestSequence === sequence.current) {
                setFailure(requestError);
            }
        } finally {
            if (requestSequence === sequence.current) {
                setBusy(null);
            }
        }
    };

    const readNext = async (): Promise<void> => {
        if (!pointer || !read || !nextReadCursor) {
            return;
        }
        const requestSequence = ++sequence.current;
        setBusy("next-read");
        clearError();
        try {
            const result = await api.readPointer({
                schema_version: "1",
                pointer: pointer.pointer,
                selector: buildSelector(selectorKind, start, end, selectorValue),
                max_bytes: 4096,
                cursor: nextReadCursor,
            });
            if (requestSequence === sequence.current) {
                setRead((current) =>
                    current
                        ? {
                              ...result,
                              content: `${current.content}${result.content}`,
                              token_count: current.token_count + result.token_count,
                          }
                        : result,
                );
                setNextReadCursor(result.next_cursor ?? null);
            }
        } catch (requestError) {
            if (requestSequence === sequence.current) {
                setFailure(requestError);
            }
        } finally {
            if (requestSequence === sequence.current) {
                setBusy(null);
            }
        }
    };

    const searchPointer = async (): Promise<void> => {
        if (!pointer || !query.trim()) {
            setError(pointer ? "검색어를 입력하세요." : "검색할 포인터를 선택하세요.");
            setErrorCode(null);
            setErrorReason(null);
            return;
        }
        const requestSequence = ++sequence.current;
        setBusy("search");
        clearError();
        setMatches([]);
        setSearchCompleted(false);
        setNextSearchCursor(null);
        try {
            const result = await api.searchPointer({
                schema_version: "1",
                pointer: pointer.pointer,
                query: query.trim(),
                limit: 20,
                max_bytes: 8192,
            });
            if (requestSequence === sequence.current) {
                setMatches(result.matches);
                setSearchCompleted(true);
                setNextSearchCursor(result.next_cursor ?? null);
            }
        } catch (requestError) {
            if (requestSequence === sequence.current) {
                setFailure(requestError);
            }
        } finally {
            if (requestSequence === sequence.current) {
                setBusy(null);
            }
        }
    };

    const searchNext = async (): Promise<void> => {
        if (!pointer || !nextSearchCursor) {
            return;
        }
        const requestSequence = ++sequence.current;
        setBusy("next-search");
        clearError();
        try {
            const result = await api.searchPointer({
                schema_version: "1",
                pointer: pointer.pointer,
                query: query.trim(),
                limit: 20,
                max_bytes: 8192,
                cursor: nextSearchCursor,
            });
            if (requestSequence === sequence.current) {
                setMatches((current) => [...current, ...result.matches]);
                setNextSearchCursor(result.next_cursor ?? null);
            }
        } catch (requestError) {
            if (requestSequence === sequence.current) {
                setFailure(requestError);
            }
        } finally {
            if (requestSequence === sequence.current) {
                setBusy(null);
            }
        }
    };

    const setFailure = (requestError: unknown): void => {
        setError(formatApiFailure(requestError, "포인터 요청에 실패했습니다."));
        const code = requestError instanceof ApiClientError ? (requestError.code ?? null) : null;
        setErrorCode(code);
        const reason = requestError instanceof ApiClientError ? requestError.details?.reason : null;
        setErrorReason(typeof reason === "string" ? reason : null);
        if (code === "SOURCE_CHANGED" || code === "EXPIRED" || code === "NOT_FOUND") {
            setRead(null);
            setMatches([]);
            setNextReadCursor(null);
            setNextSearchCursor(null);
        }
    };
    const clearError = (): void => {
        setError(null);
        setErrorCode(null);
        setErrorReason(null);
    };

    return {
        selectorKind,
        start,
        end,
        selectorValue,
        query,
        read,
        matches,
        nextReadCursor,
        nextSearchCursor,
        busy,
        searchCompleted,
        error,
        errorCode,
        errorReason,
        setSelectorKind,
        setStart,
        setEnd,
        setSelectorValue,
        setQuery: (value) => {
            setQuery(value);
            setSearchCompleted(false);
            setMatches([]);
            setNextSearchCursor(null);
        },
        readPointer,
        readNext,
        searchPointer,
        searchNext,
    };
}
