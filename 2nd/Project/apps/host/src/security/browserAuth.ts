/**
 * Browser authentication for the public API. The launcher shows a one-time
 * code; POST /auth/bootstrap exchanges it for an HttpOnly, SameSite=Strict
 * cookie scoped to /api. Tokens live only in memory: a host restart requires a
 * new bootstrap, and nothing secret is ever placed in a URL or a VITE_ variable.
 */
import { randomBytes, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE_NAME = "securecode_session";
export const SESSION_TTL_MS = 12 * 60 * 60 * 1000;
export const BOOTSTRAP_CODE_TTL_MS = 10 * 60 * 1000;
const MAX_FAILED_ATTEMPTS = 20;

export type BootstrapOutcome =
    { kind: "ok"; token: string; expiresAtMs: number } | { kind: "invalid" } | { kind: "expired" } | { kind: "locked" };

export function generateBootstrapCode(): string {
    return randomBytes(15).toString("base64url").replaceAll("_", "-");
}

function sameSecret(left: string, right: string): boolean {
    const leftBytes = Buffer.from(left, "utf8");
    const rightBytes = Buffer.from(right, "utf8");
    return leftBytes.length === rightBytes.length && timingSafeEqual(leftBytes, rightBytes);
}

export class BrowserAuth {
    private code: string | null;
    private codeExpiresAtMs: number;
    private failedAttempts = 0;
    private readonly sessions = new Map<string, number>();
    private readonly clock: () => number;

    constructor(code: string, clock: () => number) {
        this.code = code;
        this.clock = clock;
        this.codeExpiresAtMs = clock() + BOOTSTRAP_CODE_TTL_MS;
    }

    /** Called only by the authenticated local launcher; existing sessions and runs survive. */
    reissueCode(): string {
        const code = generateBootstrapCode();
        this.code = code;
        this.codeExpiresAtMs = this.clock() + BOOTSTRAP_CODE_TTL_MS;
        this.failedAttempts = 0;
        return code;
    }

    /** One successful exchange per code; repeated guessing locks the code. */
    exchange(candidate: string): BootstrapOutcome {
        if (this.code === null) return { kind: "invalid" };
        if (this.failedAttempts >= MAX_FAILED_ATTEMPTS) return { kind: "locked" };
        if (!sameSecret(candidate, this.code)) {
            this.failedAttempts += 1;
            return { kind: "invalid" };
        }
        if (this.clock() >= this.codeExpiresAtMs) {
            this.code = null;
            return { kind: "expired" };
        }
        this.code = null;
        const token = randomBytes(32).toString("hex");
        const expiresAtMs = this.clock() + SESSION_TTL_MS;
        this.sessions.set(token, expiresAtMs);
        return { kind: "ok", token, expiresAtMs };
    }

    isAuthenticated(cookieHeader: string | undefined): boolean {
        const token = readCookie(cookieHeader, SESSION_COOKIE_NAME);
        if (!token) return false;
        const expiresAtMs = this.sessions.get(token);
        if (expiresAtMs === undefined) return false;
        if (this.clock() >= expiresAtMs) {
            this.sessions.delete(token);
            return false;
        }
        return true;
    }
}

export function readCookie(header: string | undefined, name: string): string | null {
    for (const part of (header ?? "").split(";")) {
        const [rawName, ...rest] = part.trim().split("=");
        if (rawName === name) {
            const value = rest.join("=");
            return /^[0-9a-f]{64}$/.test(value) ? value : null;
        }
    }
    return null;
}

export function sessionCookie(token: string, expiresAtMs: number, nowMs: number): string {
    const maxAge = Math.max(0, Math.floor((expiresAtMs - nowMs) / 1000));
    return `${SESSION_COOKIE_NAME}=${token}; HttpOnly; SameSite=Strict; Path=/api; Max-Age=${maxAge}`;
}
