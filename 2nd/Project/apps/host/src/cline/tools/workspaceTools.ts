/**
 * Project-owned local tools registered through extraTools (3.1 S-02). They are
 * the only tools the model sees. Reads are bounded and auto-approved; writes
 * and commands need a user approval whose review shows the exact input.
 */
import { lstatSync, readdirSync, writeFileSync } from "node:fs";
import type { ExecutorCapture, RuntimePointerService, RuntimeScope } from "../adapter/ports.js";
import { refuseCommand } from "../permissions/commandPolicy.js";
import { describeStoredOutput } from "../../pointer-hooks/runtimeDescriptor.js";
import { runCommand } from "./commandRunner.js";
import { OutputCapture } from "./outputCapture.js";
import { runtimeReadTool, runtimeSearchTool } from "./runtimeTools.js";
import { field, objectSchema, review, type ProjectTool } from "./toolSupport.js";
import { resolveForRead, resolveForWrite, toRelative } from "./workspacePaths.js";

export type { ProjectTool } from "./toolSupport.js";

const WRITE_MAX_BYTES = 1024 * 1024;
const COMMAND_MAX_CHARS = 4000;
const LIST_MAX_ENTRIES = 500;
const LIST_SKIPPED = new Set([".git", ".securecode", "node_modules"]);

/** Runtime store binding for the command executor and the runtime read/search tools. */
export interface WorkspaceRuntimeOptions {
    service: RuntimePointerService;
    scope: RuntimeScope;
    thresholdBytes: number;
    maxStoredBytes: number;
    timeoutMs: number;
    /** Tells the afterTool hook that this tool call's output is already a stored pointer. */
    recordCapture(toolCallId: string, capture: ExecutorCapture): void;
}

export interface WorkspaceToolOptions {
    root: string;
    commandTimeoutMs: number;
    runtime: WorkspaceRuntimeOptions;
}

function listFilesTool(root: string): ProjectTool {
    return {
        requiresApproval: false,
        review: () => review("other", "list files", ""),
        refuse: () => null,
        tool: {
            name: "list_files",
            description: "List entries of a directory inside the workspace (default: the workspace root).",
            inputSchema: objectSchema({ path: { type: "string" } }, []),
            execute: async (input) => {
                const relativePath = field(input, "path", false) ?? ".";
                const directory = resolveForRead(root, relativePath === "" ? "." : relativePath);
                const entries = readdirSync(directory, { withFileTypes: true })
                    .filter((entry) => !LIST_SKIPPED.has(entry.name))
                    .map(
                        (entry) => `${toRelative(root, `${directory}/${entry.name}`)}${entry.isDirectory() ? "/" : ""}`,
                    )
                    .sort();
                const shown = entries.slice(0, LIST_MAX_ENTRIES);
                return (
                    shown.join("\n") +
                    (entries.length > shown.length ? `\n[${entries.length - shown.length} more]` : "")
                );
            },
        },
    };
}

function writeFileTool(root: string): ProjectTool {
    return {
        requiresApproval: true,
        review: (input) => {
            const path = field(input, "path", true);
            return review("file_change", `write ${path}`, field(input, "content", true), [path]);
        },
        refuse: () => null,
        tool: {
            name: "write_file",
            description: "Create or replace a UTF-8 text file inside the workspace. Requires user approval.",
            inputSchema: objectSchema({ path: { type: "string" }, content: { type: "string" } }, ["path", "content"]),
            execute: async (input) => {
                const content = field(input, "content", true);
                if (Buffer.byteLength(content, "utf8") > WRITE_MAX_BYTES) throw new Error("file content exceeds 1 MiB");
                const target = resolveForWrite(root, field(input, "path", true));
                writeFileSync(target, content, "utf8");
                return `wrote ${toRelative(root, target)} (${lstatSync(target).size} bytes)`;
            },
        },
    };
}

function runCommandTool(options: WorkspaceToolOptions): ProjectTool {
    const refuse = (input: unknown): string | null => {
        const command = field(input, "command", true);
        if (command.length > COMMAND_MAX_CHARS) return "command is too long";
        return refuseCommand(command);
    };
    return {
        requiresApproval: true,
        review: (input) => review("command", "run a shell command in the workspace", field(input, "command", true)),
        refuse,
        tool: {
            name: "run_command",
            description:
                "Run one shell command in the workspace root after user approval. git commit/push are refused.",
            inputSchema: objectSchema({ command: { type: "string" } }, ["command"]),
            execute: async (input, context) => {
                const refusal = refuse(input);
                if (refusal) throw new Error(refusal);
                return runCaptured(field(input, "command", true), options, context);
            },
        },
    };
}

/** Streams command output into the Runtime store once it reaches the threshold (4.4 streaming policy). */
async function runCaptured(
    command: string,
    options: WorkspaceToolOptions,
    context: { signal?: AbortSignal | undefined; toolCallId?: string | undefined },
): Promise<string> {
    const { runtime } = options;
    const signal = context.signal ?? new AbortController().signal;
    const meta = { origin: "run_command", mediaType: "text/plain", truncatedBeforeStorage: false };
    const capture = new OutputCapture({
        thresholdBytes: runtime.thresholdBytes,
        maxStoredBytes: runtime.maxStoredBytes,
        open: () => runtime.service.openUpload(runtime.scope, meta, signal),
    });
    let status: string;
    try {
        const result = await runCommand(command, {
            cwd: options.root,
            timeoutMs: options.commandTimeoutMs,
            signal: context.signal,
            onOutput: (text) => capture.append(text),
        });
        if (result.aborted) throw new Error("command aborted");
        const exit = result.timedOut ? "timed out" : `exit code ${result.exitCode ?? "none"}`;
        status = `[run_command: ${exit}]`;
    } catch (error) {
        capture.abort();
        throw error;
    }
    const outcome = await capture.finish(status).catch((error: unknown) => {
        capture.abort();
        throw error;
    });
    if (outcome.kind === "inline") return outcome.text;
    if (context.toolCallId) {
        runtime.recordCapture(context.toolCallId, {
            pointer: outcome.stored.pointer,
            byteSize: outcome.stored.byteSize,
            producedBytes: outcome.producedBytes,
            truncated: outcome.truncated,
        });
    }
    return describeStoredOutput({
        toolName: "run_command",
        pointer: outcome.stored.pointer,
        byteSize: outcome.stored.byteSize,
        preview: outcome.preview,
        status,
        facts: {},
        isError: false,
        truncation: outcome.truncated ? { producedBytes: outcome.producedBytes } : null,
    });
}

function runtimeToolOptions(runtime: WorkspaceRuntimeOptions): Parameters<typeof runtimeReadTool>[0] {
    return { service: runtime.service, scope: runtime.scope, timeoutMs: runtime.timeoutMs };
}

export function createWorkspaceTools(options: WorkspaceToolOptions): ProjectTool[] {
    return [
        listFilesTool(options.root),
        writeFileTool(options.root),
        runCommandTool(options),
        runtimeReadTool(runtimeToolOptions(options.runtime)),
        runtimeSearchTool(runtimeToolOptions(options.runtime)),
    ];
}
