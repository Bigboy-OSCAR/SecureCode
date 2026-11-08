/** Opaque CSPRNG identifiers (ws_, ses_, run_, apr_, evt_), timestamps, canonical JSON digests and safe text clipping. */
import { createHash, randomBytes } from "node:crypto";

export type IdPrefix = "ws" | "ses" | "run" | "apr" | "evt";

export function newId(prefix: IdPrefix): string {
    return `${prefix}_${randomBytes(12).toString("hex")}`;
}

export type Clock = () => number;

export const systemClock: Clock = () => Date.now();

export function isoTime(epochMs: number): string {
    return new Date(epochMs).toISOString();
}

/** Stable JSON with sorted object keys, used for idempotency and approval digests. */
export function canonicalJson(value: unknown): string {
    if (Array.isArray(value)) {
        return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
    }
    if (value !== null && typeof value === "object") {
        const entries = Object.entries(value as Record<string, unknown>)
            .filter(([, item]) => item !== undefined)
            .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
        return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(",")}}`;
    }
    return JSON.stringify(value) ?? "null";
}

export function sha256Hex(text: string): string {
    return createHash("sha256").update(text, "utf8").digest("hex");
}

/** Cuts a string to at most maxChars UTF-16 units without splitting a surrogate pair. */
export function clipText(text: string, maxChars: number): string {
    if (text.length <= maxChars) return text;
    let end = maxChars;
    const code = text.charCodeAt(end - 1);
    if (code >= 0xd800 && code <= 0xdbff) end -= 1;
    return text.slice(0, end);
}
