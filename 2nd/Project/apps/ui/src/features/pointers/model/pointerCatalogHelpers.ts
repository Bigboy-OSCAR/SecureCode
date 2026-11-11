import type { PointerListQuery, SessionId } from "@securecode/contracts";
import type { UiPointer } from "../../../api/mappers/pointerMapper.js";

export interface PointerPage {
    items: UiPointer[];
    nextCursor: string | null;
    hasMore: boolean;
}

export function emptyPage(): PointerPage {
    return { items: [], nextCursor: null, hasMore: false };
}

export function toPointerPage(
    items: UiPointer[],
    page: { next_cursor: string | null; has_more: boolean },
): PointerPage {
    return { items, nextCursor: page.next_cursor, hasMore: page.has_more };
}

export function mergePointers(current: UiPointer[], incoming: UiPointer[]): UiPointer[] {
    const byPointer = new Map(current.map((item) => [item.pointer, item]));
    for (const item of incoming) {
        byPointer.set(item.pointer, item);
    }
    return [...byPointer.values()];
}

export function replacePointer(current: UiPointer[], oldPointer: string, incoming: UiPointer[]): UiPointer[] {
    return mergePointers(
        current.filter((item) => item.pointer !== oldPointer),
        incoming,
    );
}

export function createListQuery(
    kind: "source" | "runtime",
    sessionId: SessionId | null,
    cursor?: string,
): PointerListQuery | null {
    if (kind === "source") {
        return { kind, limit: 100, ...(cursor ? { cursor } : {}) };
    }
    return sessionId ? { kind, session_id: sessionId, limit: 100, ...(cursor ? { cursor } : {}) } : null;
}
