/**
 * Project-owned local tools registered through `extraTools`. They run inside the
 * SDK's local execution path, so `beforeTool`/`afterTool` hooks apply to them.
 * Tool input arrives as `unknown` from the model and is validated here.
 */
import type { AgentTool } from "@cline/sdk";

export const SENTINEL_TOOL_NAME = "probe_generate_log";
export const COMMAND_TOOL_NAME = "probe_run_command";
export const SENTINEL_MARKER = "SECURECODE_SENTINEL_RAW_7F3A";

/** 64 KiB of log lines, each carrying the sentinel marker. */
export const SENTINEL_OUTPUT_BYTES = 64 * 1024;

export interface CommandToolCounter {
    executions: number;
    abortedExecutions?: number;
}

function readStringField(input: unknown, fieldName: string): string {
    if (typeof input === "object" && input !== null) {
        const value = (input as Record<string, unknown>)[fieldName];
        if (typeof value === "string") {
            return value;
        }
    }
    throw new Error(`tool input field "${fieldName}" must be a string`);
}

function waitUnlessAborted(signal: AbortSignal | undefined, delayMs: number): Promise<void> {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, delayMs);
        signal?.addEventListener("abort", () => {
            clearTimeout(timer);
            reject(new Error("command aborted"));
        }, { once: true });
    });
}

export function buildSentinelOutput(): string {
    const line = `${SENTINEL_MARKER} line payload ${"x".repeat(64)}\n`;
    const repeatCount = Math.ceil(SENTINEL_OUTPUT_BYTES / line.length);
    return line.repeat(repeatCount).slice(0, SENTINEL_OUTPUT_BYTES);
}

export function createSentinelTool(): AgentTool {
    return {
        name: SENTINEL_TOOL_NAME,
        description: "Produces a large fixture log for the SDK probe.",
        inputSchema: {
            type: "object",
            properties: { label: { type: "string" } },
            required: ["label"],
            additionalProperties: false,
        },
        execute: async (input) => {
            readStringField(input, "label");
            return buildSentinelOutput();
        },
    };
}

/** Fake command tool: never spawns a process, only counts executions. */
export function createCommandTool(counter: CommandToolCounter, delayMs = 50): AgentTool {
    return {
        name: COMMAND_TOOL_NAME,
        description: "Runs a fixture command after approval.",
        inputSchema: {
            type: "object",
            properties: { command: { type: "string" } },
            required: ["command"],
            additionalProperties: false,
        },
        execute: async (input, context) => {
            const command = readStringField(input, "command");
            counter.executions += 1;
            await waitUnlessAborted(context.signal, delayMs).catch((error: unknown) => {
                counter.abortedExecutions = (counter.abortedExecutions ?? 0) + 1;
                throw error;
            });
            return `fixture command finished: ${command}`;
        },
    };
}
