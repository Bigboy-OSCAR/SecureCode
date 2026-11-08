/**
 * Services the public routes depend on. app/ assembles them; routes only see
 * these SDK-independent shapes (the AgentRuntime port, not ClineCore).
 */
import type { ContractValidator, ProtectionState, SettingsResponse } from "@securecode/contracts";
import type { ContextServiceClient } from "../context-client/ports.js";
import type { BrowserAuth } from "../security/browserAuth.js";
import type { Clock } from "../security/ids.js";
import type { WorkspaceRegistry } from "./projects/workspaceRegistry.js";
import type { RunService } from "./runs/runService.js";
import type { SessionStore } from "./sessions/sessionStore.js";
import type { IdempotencyStore } from "./shared/idempotency.js";

export interface RouteServices {
    validator: ContractValidator;
    contextClient: ContextServiceClient;
    auth: BrowserAuth;
    workspaces: WorkspaceRegistry;
    sessions: SessionStore;
    runs: RunService;
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
