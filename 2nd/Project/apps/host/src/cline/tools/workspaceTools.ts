/**
 * Project-owned local tools registered through extraTools (3.1 S-02). They are
 * the only tools the model sees. Reads are bounded and auto-approved; writes
 * and commands need a user approval whose review shows the exact input.
 */
import { lstatSync, readdirSync, writeFileSync } from "node:fs";
import type { AgentTool } from "@cline/sdk";
import type { ApprovalReview } from "@securecode/contracts";
import { refuseCommand } from "../permissions/commandPolicy.js";
import { runCommand } from "./commandRunner.js";
import { readBoundedUtf8 } from "./boundedFileRead.js";
import { readRuntimePointer, type RuntimePointerHookOptions } from "../../pointer-hooks/runtimePointerHook.js";
import { resolveForRead, resolveForWrite, toRelative } from "./workspacePaths.js";

export const REVIEW_MAX_BYTES = 16 * 1024;
const READ_DEFAULT_BYTES = 16 * 1024;
const READ_MAX_BYTES = 64 * 1024;
const WRITE_MAX_BYTES = 1024 * 1024;
const COMMAND_MAX_CHARS = 4000;
const COMMAND_OUTPUT_MAX_BYTES = 1024 * 1024;
const LIST_MAX_ENTRIES = 500;
const LIST_SKIPPED = new Set([".git", ".securecode", "node_modules"]);

export interface ProjectTool {
    tool: AgentTool;
    requiresApproval: boolean;
    review(input: unknown): ApprovalReview;
    /** Non-null reason means the host refuses without asking the user. */
    refuse(input: unknown): string | null;
}

export interface WorkspaceToolOptions {
    root: string;
    commandTimeoutMs: number;
    pointer: Pick<RuntimePointerHookOptions, "baseUrl" | "internalToken" | "api" | "workspaceId" | "sessionId">;
}

function field(input: unknown, name: string, required: true): string;
function field(input: unknown, name: string, required: false): string | undefined;
function field(input: unknown, name: string, required: boolean): string | undefined {
    const value = typeof input === "object" && input !== null ? (input as Record<string, unknown>)[name] : undefined;
    if (value === undefined && !required) return undefined;
    if (typeof value !== "string") throw new Error(`tool input field "${name}" must be a string`);
    return value;
}

/** Cuts text to a UTF-8 byte budget without splitting a character. */
export function clipUtf8(text: string, maxBytes: number): { text: string; truncated: boolean } {
    const bytes = Buffer.from(text, "utf8");
    if (bytes.length <= maxBytes) return { text, truncated: false };
    let end = maxBytes;
    while (end > 0 && ((bytes[end] ?? 0) & 0xc0) === 0x80) end -= 1;
    return { text: bytes.subarray(0, end).toString("utf8"), truncated: true };
}

function review(kind: ApprovalReview["kind"], summary: string, content: string, paths?: string[]): ApprovalReview {
    const clipped = clipUtf8(content, REVIEW_MAX_BYTES);
    return {
        kind,
        summary: summary.slice(0, 500),
        content: clipped.text,
        content_truncated: clipped.truncated,
        reviewable: !clipped.truncated,
        ...(paths ? { target_paths: paths } : {}),
    };
}

const objectSchema = (properties: Record<string, unknown>, required: string[]): AgentTool["inputSchema"] => ({
    type: "object",
    properties,
    required,
    additionalProperties: false,
});

function readFileTool(root: string): ProjectTool {
    return {
        requiresApproval: false,
        review: (input) => review("other", `read ${field(input, "path", true)}`, ""),
        refuse: () => null,
        tool: {
            name: "read_file",
            description: "Read part of a UTF-8 text file inside the workspace (at most 64 KiB per call).",
            inputSchema: objectSchema(
                {
                    path: { type: "string" },
                    offset_bytes: { type: "integer", minimum: 0 },
                    max_bytes: { type: "integer", minimum: 1, maximum: READ_MAX_BYTES },
                },
                ["path"],
            ),
            execute: async (input) => {
                const target = resolveForRead(root, field(input, "path", true));
                const record = input as { offset_bytes?: number; max_bytes?: number };
                const offset = Number.isSafeInteger(record.offset_bytes) ? Math.max(0, record.offset_bytes ?? 0) : 0;
                const limit = Math.min(
                    READ_MAX_BYTES,
                    Number.isSafeInteger(record.max_bytes) ? (record.max_bytes ?? 1) : READ_DEFAULT_BYTES,
                );
                return readBoundedUtf8(target, offset, limit);
            },
        },
    };
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
                const result = await runCommand(field(input, "command", true), {
                    cwd: options.root,
                    timeoutMs: options.commandTimeoutMs,
                    maxOutputBytes: COMMAND_OUTPUT_MAX_BYTES,
                    signal: context.signal,
                });
                if (result.aborted) throw new Error("command aborted");
                const status = result.timedOut ? "timed out" : `exit code ${result.exitCode ?? "none"}`;
                return `${result.output}${result.truncated ? "\n[output truncated at 1 MiB]" : ""}\n[run_command: ${status}]`;
            },
        },
    };
}

function runtimeReadTool(pointer: WorkspaceToolOptions["pointer"]): ProjectTool {
    return {
        requiresApproval: false,
        review: () => review("other", "read runtime pointer", ""),
        refuse: () => null,
        tool: {
            name: "runtime_read",
            description: "Read a bounded slice of a Runtime Pointer owned by this session.",
            inputSchema: objectSchema(
                {
                    pointer: { type: "string" },
                    offset: { type: "integer", minimum: 0 },
                    max_bytes: { type: "integer", minimum: 1, maximum: 16384 },
                },
                ["pointer"],
            ),
            execute: async (input) => {
                const record = input as { pointer?: string; offset?: number; max_bytes?: number };
                const result = await readRuntimePointer(
                    field(record, "pointer", true),
                    pointer,
                    Number.isSafeInteger(record.offset) ? (record.offset ?? 0) : 0,
                    Number.isSafeInteger(record.max_bytes) ? (record.max_bytes ?? 16384) : 16384,
                );
                return JSON.stringify(result);
            },
        },
    };
}

function runtimeSearchTool(pointer: WorkspaceToolOptions["pointer"]): ProjectTool {
    return {
        requiresApproval: false,
        review: () => review("other", "search runtime pointer", ""),
        refuse: () => null,
        tool: {
            name: "runtime_search",
            description: "Search a Runtime Pointer owned by this session and return matching line numbers.",
            inputSchema: objectSchema(
                {
                    pointer: { type: "string" },
                    query: { type: "string" },
                },
                ["pointer", "query"],
            ),
            execute: async (input) => {
                const record = input as { pointer?: string; query?: string };
                const result = await readRuntimePointer(field(record, "pointer", true), pointer);
                const query = field(record, "query", true).toLowerCase();
                const lines = result.content.split("\n");
                const matches: { line: number; text: string }[] = [];
                for (let index = 0; index < lines.length; index += 1) {
                    const line = lines[index] ?? "";
                    if (line.toLowerCase().includes(query)) {
                        matches.push({ line: index + 1, text: line });
                    }
                }
                return JSON.stringify({ matches, byte_size: result.byteSize, truncated: result.truncated });
            },
        },
    };
}

export function createWorkspaceTools(options: WorkspaceToolOptions): ProjectTool[] {
    return [
        readFileTool(options.root),
        listFilesTool(options.root),
        writeFileTool(options.root),
        runCommandTool(options),
        runtimeReadTool(options.pointer),
        runtimeSearchTool(options.pointer),
    ];
}
