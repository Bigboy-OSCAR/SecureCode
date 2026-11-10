/**
 * The complete model-visible tool set of one session (3.6) and its allow list. Every content path is
 * served by our boundaries: workspace file text by the Source adapter (read_file, search_file), code
 * search by R0 (code_search, code_read), command and large outputs by the Runtime adapter
 * (run_command executor, runtime_read/search), PDFs by the PDF page reader. list_files shows names only
 * and write_file needs approval. SDK built-in tools stay disabled (enableTools=false, 3.1 C-04), and the
 * fetch gate refuses any request exposing a tool outside ALLOWED_TOOL_NAMES.
 */
import type { ExplicitContextRef } from "@securecode/contracts";
import type { ContextServiceClient } from "../../context-client/ports.js";
import type { RuntimePointerService } from "../adapter/ports.js";
import type { WorkspaceRuntimeOptions } from "./workspaceTools.js";
import { createWorkspaceTools } from "./workspaceTools.js";
import { codeTools } from "./codeTools.js";
import { PDF_TOOL_NAMES, pdfTools } from "./pdfTools.js";
import { sourceTools } from "./sourceTools.js";
import type { ProjectTool } from "./toolSupport.js";

export const ALLOWED_TOOL_NAMES: ReadonlySet<string> = new Set([
    "read_file",
    "search_file",
    "list_files",
    "write_file",
    "run_command",
    "runtime_read",
    "runtime_search",
    "code_search",
    "code_read",
    ...PDF_TOOL_NAMES,
]);

export interface SessionToolOptions {
    root: string;
    workspaceId: string;
    commandTimeoutMs: number;
    serviceTimeoutMs: number;
    client: ContextServiceClient;
    runtime: WorkspaceRuntimeOptions;
    readonly recordShown: (ref: ExplicitContextRef) => void;
}

export function buildSessionTools(options: SessionToolOptions): ProjectTool[] {
    const shared = {
        workspaceId: options.workspaceId,
        timeoutMs: options.serviceTimeoutMs,
        recordShown: options.recordShown,
    };
    const tools = [
        ...sourceTools({ ...shared, sources: options.client.sources, root: options.root }),
        ...createWorkspaceTools({
            root: options.root,
            commandTimeoutMs: options.commandTimeoutMs,
            runtime: options.runtime,
        }),
        ...codeTools({ ...shared, symbols: options.client.symbols }),
        ...pdfTools({
            service: options.client.pdf,
            workspaceId: options.workspaceId,
            timeoutMs: options.serviceTimeoutMs,
        }),
    ];
    const unknown = tools.filter((entry) => !ALLOWED_TOOL_NAMES.has(entry.tool.name));
    if (unknown.length > 0 || tools.length !== ALLOWED_TOOL_NAMES.size) {
        throw new Error("session tools and the allow list differ");
    }
    return tools;
}

/** Tool definitions as the model sees them (name, description, input schema), for the Selector's cost. */
export function toolSchemaText(tools: readonly ProjectTool[]): string {
    return JSON.stringify(
        tools.map((entry) => ({
            name: entry.tool.name,
            description: entry.tool.description,
            input_schema: entry.tool.inputSchema,
        })),
    );
}

/** Tool definitions text of a session; tool execution is never reached, so placeholders are safe. */
export function sessionToolSchema(client: ContextServiceClient, runtime: RuntimePointerService | null): string {
    const placeholder = "ws_00000000";
    return toolSchemaText(
        buildSessionTools({
            root: ".",
            workspaceId: placeholder,
            commandTimeoutMs: 1,
            serviceTimeoutMs: 1,
            client,
            recordShown: () => undefined,
            runtime: {
                service: runtime as RuntimePointerService,
                scope: { workspaceId: placeholder, sessionId: "ses_00000000" },
                thresholdBytes: 1,
                maxStoredBytes: 1,
                timeoutMs: 1,
                recordCapture: () => undefined,
            },
        }),
    );
}
