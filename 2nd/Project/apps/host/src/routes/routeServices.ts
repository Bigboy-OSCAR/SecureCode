/**
 * Services the public routes depend on. app/ assembles them; routes only see
 * these SDK-independent shapes (the AgentRuntime port, not ClineCore).
 */
import type { ContractValidator, ProtectionState, SettingsResponse } from "@securecode/contracts";
import type { ContextServiceClient } from "../context-client/ports.js";
import type { BrowserAuth } from "../security/browserAuth.js";
import type { Clock } from "../security/ids.js";
import type { RuntimePointerService } from "../cline/adapter/ports.js";
import type { ContextAssembler } from "../cline/context/contextAssembler.js";
import type { ServiceWorkspaces } from "./projects/serviceWorkspaces.js";
import type { WorkspaceRegistry } from "./projects/workspaceRegistry.js";
import type { RunService } from "./runs/runService.js";
import type { SessionStore } from "./sessions/sessionStore.js";
import type { IdempotencyStore } from "./shared/idempotency.js";

import type { ModelManager } from "../app/models/modelManager.js";

export interface RouteServices {
    models?: ModelManager;
    launcherToken?: string;
    validator: ContractValidator;
    contextClient: ContextServiceClient;
    auth: BrowserAuth;
    workspaces: WorkspaceRegistry;
    sessions: SessionStore;
    runs: RunService;
    /** context.select for previews and runs (3.6). */
    assembler: ContextAssembler;
    /** Registers workspace roots with the context-service before Source/R0/PDF calls. */
    serviceWorkspaces: ServiceWorkspaces;
    /** PDF job ID → workspace, for GET /pdf/jobs/:job_id (jobs are workspace-scoped in the service). */
    pdfJobs: Map<string, string>;
    /** 4.3 Runtime store client for public Runtime Pointer reads (null blocks them). */
    runtimePointers: RuntimePointerService | null;
    idempotency: IdempotencyStore;
    protections: () => ProtectionState[];
    settings: () => SettingsResponse;
    clock: Clock;
    /** Keep-alive comment interval for SSE (EVENTS.md 4); tests shorten it. */
    sseKeepAliveMs: number;
}

export function requestUrl(rawUrl: string | undefined): URL {
    return new URL(rawUrl ?? "/", "http://host.invalid");
}
