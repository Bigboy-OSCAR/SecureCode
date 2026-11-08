/**
 * Assembles stores, the approval broker, the SDK runtime (through a factory
 * so @cline/sdk is imported only after the Cline home is prepared) and the
 * HTTP server. Production passes null for the 4.4/4.8 hooks, which keeps the
 * protections unavailable and blocks sessions; tests inject fixture hooks.
 */
import type { Server } from "node:http";
import { join } from "node:path";
import type { ContractValidator } from "@securecode/contracts";
import type { ClineRuntimeOptions } from "../cline/adapter/clineRuntime.js";
import type { ModelRequestGate, ToolResultTransformer } from "../cline/adapter/ports.js";
import type { AgentRuntime } from "../cline/adapter/runtimePort.js";
import { ApprovalBroker } from "../cline/permissions/approvalBroker.js";
import type { HostConfig } from "../config/hostConfig.js";
import type { ProviderCredentials, RuntimeConfig } from "../config/runtimeConfig.js";
import type { ContextServiceClient } from "../context-client/ports.js";
import type { Logger } from "../logging/logger.js";
import { WorkspaceRegistry } from "../routes/projects/workspaceRegistry.js";
import { RunService } from "../routes/runs/runService.js";
import { SessionStore } from "../routes/sessions/sessionStore.js";
import { IdempotencyStore } from "../routes/shared/idempotency.js";
import { BrowserAuth, generateBootstrapCode } from "../security/browserAuth.js";
import { systemClock, type Clock } from "../security/ids.js";
import { createHostServer } from "./server.js";
import { buildSettings } from "./settingsView.js";

export interface HostAssemblyOptions {
    hostConfig: HostConfig;
    runtimeConfig: RuntimeConfig;
    credentials: ProviderCredentials;
    contextClient: ContextServiceClient;
    validator: ContractValidator;
    logger: Logger;
    runtimeFactory: (options: ClineRuntimeOptions) => Promise<AgentRuntime>;
    transformer: ToolResultTransformer | null;
    gate: ModelRequestGate | null;
    providerFetch?: typeof fetch;
    clock?: Clock;
    sseKeepAliveMs?: number;
}

export interface AssembledHost {
    server: Server;
    bootstrapCode: string;
    bootstrapCodeGenerated: boolean;
    runtime: AgentRuntime;
    shutdown(): Promise<void>;
}

export async function assembleHost(options: HostAssemblyOptions): Promise<AssembledHost> {
    const clock = options.clock ?? systemClock;
    const { hostConfig, runtimeConfig } = options;
    const stateDir = join(hostConfig.dataDir, "host");
    const broker = new ApprovalBroker(runtimeConfig.approvalTimeoutMs, clock);
    const runtime = await options.runtimeFactory({
        providerId: hostConfig.providerId,
        modelId: hostConfig.modelId,
        apiKey: options.credentials.apiKey,
        baseUrl: runtimeConfig.providerBaseUrl,
        maxOutputTokens: runtimeConfig.maxOutputTokens,
        hookTimeoutMs: runtimeConfig.hookTimeoutMs,
        commandTimeoutMs: runtimeConfig.commandTimeoutMs,
        broker,
        transformer: options.transformer,
        gate: options.gate,
        ...(options.providerFetch ? { providerFetch: options.providerFetch } : {}),
    });
    const idempotency = new IdempotencyStore(join(stateDir, "idempotency"), clock);
    const workspaces = new WorkspaceRegistry(
        join(stateDir, "workspaces"),
        runtimeConfig.allowedWorkspaceRoots,
        idempotency,
        clock,
    );
    const sessions = new SessionStore(join(stateDir, "sessions"), clock);
    const runs = new RunService({
        runtime,
        broker,
        sessions,
        workspaces,
        idempotency,
        runsDirectory: join(stateDir, "runs"),
        clock,
    });
    const bootstrapCode = runtimeConfig.bootstrapCode ?? generateBootstrapCode();
    const providerConfigured = (): boolean => options.credentials.apiKey !== null;
    const server = createHostServer({
        originPolicy: { allowedOrigins: hostConfig.allowedOrigins, allowedHosts: hostConfig.allowedHosts },
        logger: options.logger,
        providerConfigured,
        services: {
            validator: options.validator,
            contextClient: options.contextClient,
            auth: new BrowserAuth(bootstrapCode, clock),
            workspaces,
            sessions,
            runs,
            idempotency,
            protections: () => runtime.protections(),
            settings: () => buildSettings(hostConfig, runtimeConfig, providerConfigured(), runtime.protections()),
            clock,
            sseKeepAliveMs: options.sseKeepAliveMs ?? 15000,
        },
    });
    return {
        server,
        bootstrapCode,
        bootstrapCodeGenerated: runtimeConfig.bootstrapCode === null,
        runtime,
        shutdown: async () => {
            await new Promise<void>((resolve) => server.close(() => resolve()));
            await runtime.dispose();
        },
    };
}
