/**
 * Same-origin and DNS-rebinding guard for the public /api/v1 surface.
 * Session cookies are HttpOnly + SameSite=Strict (3.5); this guard also rejects
 * foreign Host headers and cross-origin or origin-less state-changing requests.
 */
import type { ErrorCode } from "@securecode/contracts";

export interface OriginPolicy {
    allowedOrigins: readonly string[];
    allowedHosts: readonly string[];
}

export interface GuardedRequest {
    method: string;
    headers: Readonly<Record<string, string | string[] | undefined>>;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function headerValue(request: GuardedRequest, name: string): string | undefined {
    const value = request.headers[name];
    return Array.isArray(value) ? value[0] : value;
}

/** Returns the rejection code, or null when the request may proceed. */
export function checkRequestOrigin(request: GuardedRequest, policy: OriginPolicy): ErrorCode | null {
    const host = headerValue(request, "host");
    if (!host || !policy.allowedHosts.includes(host.toLowerCase())) {
        return "ORIGIN_REJECTED";
    }

    if (headerValue(request, "sec-fetch-site") === "cross-site") {
        return "ORIGIN_REJECTED";
    }

    const origin = headerValue(request, "origin");
    if (origin !== undefined && !policy.allowedOrigins.includes(origin)) {
        return "ORIGIN_REJECTED";
    }
    if (!SAFE_METHODS.has(request.method.toUpperCase()) && origin === undefined) {
        return "ORIGIN_REJECTED";
    }
    return null;
}
