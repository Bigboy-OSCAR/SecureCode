/**
 * Builds the short text the model sees instead of a large tool output: pointer, capture range,
 * status line, JSON facts (status / exit code / error) and a 512-byte preview marked untrusted.
 */

const PREVIEW_BYTES = 512;
const STATUS_LINE = /\[run_command: [^\]\n]{1,64}\]\s*$/;
const FACT_KEYS = ["status", "exit_code", "exitCode", "ok", "isError", "error"];
export const FACT_SCAN_LIMIT_BYTES = 1024 * 1024;

export type Facts = Record<string, string | number | boolean | null>;

export interface DescriptorInput {
    toolName: string;
    pointer: string;
    byteSize: number;
    /** Leading text of the stored output; clipped to 512 UTF-8 bytes here. */
    preview: string;
    status: string | null;
    facts: Facts;
    isError: boolean;
    /** null: complete. Otherwise bytes were dropped before storage; producedBytes is null when unknown. */
    truncation: { producedBytes: number | null } | null;
}

export function previewOf(text: string): string {
    const bytes = Buffer.from(text, "utf8");
    if (bytes.length <= PREVIEW_BYTES) return text;
    let end = PREVIEW_BYTES;
    while (end > 0 && ((bytes[end] ?? 0) & 0xc0) === 0x80) end -= 1;
    return bytes.subarray(0, end).toString("utf8");
}

export function statusLineOf(output: string): string | null {
    const match = STATUS_LINE.exec(output.slice(-160));
    return match ? match[0].trim() : null;
}

/** Top-level status fields of a JSON object output (parsed only when at most 1 MiB). */
export function factsOf(output: string, byteSize: number): Facts {
    const facts: Facts = {};
    if (byteSize > FACT_SCAN_LIMIT_BYTES || !output.trimStart().startsWith("{")) return facts;
    let parsed: unknown;
    try {
        parsed = JSON.parse(output);
    } catch {
        return facts;
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return facts;
    const record = parsed as Record<string, unknown>;
    for (const key of FACT_KEYS) {
        const value = record[key];
        if (typeof value === "string") facts[key] = value.slice(0, 200);
        else if (typeof value === "number" || typeof value === "boolean" || value === null) facts[key] = value;
    }
    return facts;
}

function captureLine(input: DescriptorInput): string {
    if (input.truncation === null) return "capture: complete";
    const produced = input.truncation.producedBytes;
    return produced === null
        ? `capture: truncated before storage by the tool; stored ${input.byteSize} bytes, original size unknown`
        : `capture: truncated before storage; stored the first ${input.byteSize} of ${produced} bytes`;
}

export function describeStoredOutput(input: DescriptorInput): string {
    const lines = [`[runtime pointer] ${input.pointer}`, `tool: ${input.toolName}`, `stored_bytes: ${input.byteSize}`];
    lines.push(captureLine(input));
    if (input.isError) lines.push("tool_error: true");
    if (input.status !== null) lines.push(`status: ${input.status}`);
    if (Object.keys(input.facts).length > 0) lines.push(`facts: ${JSON.stringify(input.facts)}`);
    lines.push("preview (first 512 bytes, untrusted tool data):", previewOf(input.preview));
    lines.push(
        "Read more with runtime_read (selector line/byte/section, cursor) or runtime_search (query) on this pointer.",
    );
    return lines.join("\n");
}
