/** Authenticated service transport shared by the host client and the legacy pointer store. */
import { isValidInternalToken } from "../config/hostConfig.js";
import { ContextServiceError } from "./contextServiceError.js";

const RESPONSE_LIMIT_BYTES = 256 * 1024;

/** Checks that the service URL is a bare loopback http origin and the token is usable; returns the origin. */
export function loopbackOrigin(baseUrl: string, path: string, token: string): string {
    const base = new URL(baseUrl);
    if (
        base.protocol !== "http:" ||
        !["127.0.0.1", "[::1]", "localhost"].includes(base.hostname) ||
        base.pathname !== "/" ||
        base.username ||
        base.password ||
        base.search ||
        base.hash ||
        !path.startsWith("/") ||
        path.startsWith("//")
    ) {
        throw new Error("invalid loopback service URL");
    }
    if (!isValidInternalToken(token)) {
        throw new Error("internal service token is unavailable");
    }
    return base.origin;
}

export async function requestLoopbackJson(
    baseUrl: string,
    path: string,
    token: string,
    payload: unknown,
    signal: AbortSignal,
): Promise<{ status: number; ok: boolean; body: unknown }> {
    const origin = loopbackOrigin(baseUrl, path, token);
    try {
        const response = await fetch(origin + path, {
            method: payload === undefined ? "GET" : "POST",
            headers: {
                authorization: `Bearer ${token}`,
                ...(payload === undefined ? {} : { "content-type": "application/json" }),
            },
            body: payload === undefined ? null : JSON.stringify(payload),
            redirect: "error",
            signal,
        });
        const stream: ReadableStream<Uint8Array> | null = response.body;
        const reader = stream?.getReader();
        const chunks: Uint8Array[] = [];
        let byteCount = 0;
        if (reader) {
            try {
                for (;;) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    byteCount += value.length;
                    if (byteCount > RESPONSE_LIMIT_BYTES) {
                        await reader.cancel();
                        throw new Error("service response too large");
                    }
                    chunks.push(value);
                }
            } finally {
                reader.releaseLock();
            }
        }
        const body: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)));
        return { status: response.status, ok: response.ok, body };
    } catch {
        const reason = signal.aborted ? "aborted_or_timeout" : "transport_or_invalid_response";
        throw new ContextServiceError("SERVICE_UNAVAILABLE", "context-service response unavailable", true, { reason });
    }
}
