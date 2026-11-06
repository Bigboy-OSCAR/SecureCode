/**
 * Offset pages over an already ordered list. Cursors are opaque base64url
 * tokens bound to a scope string (list kind + owner id), so a cursor from
 * another list or owner is rejected as VALIDATION_FAILED.
 */
import type { PageInfo } from "@securecode/contracts";
import { RouteFailure } from "./routeFailure.js";

export const DEFAULT_PAGE_LIMIT = 20;
export const MAX_PAGE_LIMIT = 100;

export interface PageRequestInput {
    limit?: number;
    cursor?: string;
}

export function encodeCursor(scope: string, offset: number): string {
    return Buffer.from(JSON.stringify({ s: scope, o: offset }), "utf8").toString("base64url");
}

function decodeCursor(scope: string, cursor: string): number {
    try {
        const decoded = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8")) as { s?: unknown; o?: unknown };
        if (decoded.s === scope && typeof decoded.o === "number" && Number.isSafeInteger(decoded.o) && decoded.o >= 0) {
            return decoded.o;
        }
    } catch {
        // fall through to the validation error
    }
    throw new RouteFailure("VALIDATION_FAILED", "cursor is not valid for this list", { reason: "cursor" });
}

export function readPageQuery(url: URL): PageRequestInput {
    const result: PageRequestInput = {};
    const limit = url.searchParams.get("limit");
    if (limit !== null) {
        const parsed = Number(limit);
        if (!Number.isInteger(parsed) || parsed < 1 || parsed > MAX_PAGE_LIMIT) {
            throw new RouteFailure("VALIDATION_FAILED", "limit must be an integer between 1 and 100", {
                reason: "limit",
            });
        }
        result.limit = parsed;
    }
    const cursor = url.searchParams.get("cursor");
    if (cursor !== null) {
        if (cursor.length < 1 || cursor.length > 512) {
            throw new RouteFailure("VALIDATION_FAILED", "cursor is not valid for this list", { reason: "cursor" });
        }
        result.cursor = cursor;
    }
    return result;
}

export function paginate<T>(
    items: readonly T[],
    scope: string,
    request: PageRequestInput,
): { items: T[]; page: PageInfo } {
    const limit = request.limit ?? DEFAULT_PAGE_LIMIT;
    const offset = request.cursor ? decodeCursor(scope, request.cursor) : 0;
    const slice = items.slice(offset, offset + limit);
    const next = offset + slice.length;
    const hasMore = next < items.length;
    return {
        items: slice,
        page: { limit, next_cursor: hasMore ? encodeCursor(scope, next) : null, has_more: hasMore },
    };
}
