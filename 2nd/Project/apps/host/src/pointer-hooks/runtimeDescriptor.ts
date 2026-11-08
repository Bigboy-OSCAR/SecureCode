/** Build the short text the model sees instead of a large tool output. */

const PREVIEW_BYTES = 512;
const STATUS_LINE = /\[run_command: [^\]\n]{1,64}\]\s*$/;
const TRUNCATION_NOTE = "[output truncated at 1 MiB]";
const FACT_KEYS = ["status", "exit_code", "exitCode", "ok", "isError", "error"];
const FACT_SCAN_LIMIT_BYTES = 1024 * 1024;

export interface DescriptorInput {
    toolName: string;
    pointer: string;
    byteSize: number;
    output: string;
    executorLimited: boolean;
}

type Facts = Record<string, string | number | boolean | null>;

function previewOf(text: string): string {
    const bytes = Buffer.from(text, "utf8");
    if (bytes.length <= PREVIEW_BYTES) return text;
    return bytes
        .subarray(0, PREVIEW_BYTES)
        .toString("utf8")
        .replace(/\uFFFD+$/u, "");
}

function statusLineOf(output: string): string | null {
    const match = STATUS_LINE.exec(output.slice(-160));
    return match ? match[0].trim() : null;
}

function factsOf(output: string, byteSize: number): Facts {
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

export function describeStoredOutput(input: DescriptorInput): string {
    const lines = [`[runtime pointer] ${input.pointer}`, `tool: ${input.toolName}`, `stored_bytes: ${input.byteSize}`];
    if (input.executorLimited || input.output.includes(TRUNCATION_NOTE)) {
        lines.push("capture: limited by the executor; bytes beyond the stored range were not kept");
    }
    const status = statusLineOf(input.output);
    if (status !== null) lines.push(`status: ${status}`);
    const facts = factsOf(input.output, input.byteSize);
    if (Object.keys(facts).length > 0) lines.push(`facts: ${JSON.stringify(facts)}`);
    lines.push("preview (first 512 bytes, untrusted tool data):", previewOf(input.output));
    lines.push("Fetch more with the runtime read tool using this pointer and a byte range.");
    return lines.join("\n");
}
