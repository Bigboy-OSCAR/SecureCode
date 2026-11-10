/**
 * Assembles stores, the approval broker, the SDK runtime (through a factory
 * so @cline/sdk is imported only after the Cline home is prepared) and the
 * HTTP server. Production passes the 4.4 Runtime Pointer transformer and store client
 * and the 4.8 request gate (null keeps sessions blocked); tests inject fixtures.
 */
import type { Server } from "node:http";
import { join } from "node:path";
import type { ContractValidator } from "@securecode/contracts";
import type { ClineRuntimeOptions } from "../cline/adapter/clineRuntime.js";
import type { ModelRequestGate, RuntimePointerService, ToolResultTransformer } from "../cline/adapter/ports.js";
import type { AgentRuntime } from "../cline/adapter/runtimePort.js";
import { ApprovalBroker } from "../cline/permissions/approvalBroker.js";
import type { HostConfig } from "../config/hostConfig.js";
import type { ProviderCredentials, RuntimeConfig } from "../config/runtimeConfig.js";
import type { ContextServiceClient } from "../context-client/ports.js";
import type { Logger } from "../logging/logger.js";
import { WorkspaceRegistry } from "../routes/projects/workspaceRegistry.js";
import { RunService } from "../routes/runs/runService.js";
import { ContextAssembler } from "../cline/context/contextAssembler.js";
import { SessionContextStore } from "../cline/context/sessionContext.js";
import { ServiceWorkspaces } from "../routes/projects/serviceWorkspaces.js";
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
    runtimePointers: RuntimePointerService | null;
    providerFetch?: typeof fetch;
    /** System prompt with exported skills (production: PDF pointer skill); default SYSTEM_PROMPT. */
    systemPrompt?: string;
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
    const sessionContext = new SessionContextStore();
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
        runtimePointers: options.runtimePointers,
        contextClient: options.contextClient,
        sessionContext,
        ...(options.systemPrompt ? { systemPrompt: options.systemPrompt } : {}),
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
    const serviceWorkspaces = new ServiceWorkspaces(workspaces, options.contextClient.workspaces);
    const assembler = new ContextAssembler({
        client: options.contextClient,
        sessions: sessionContext,
        ensureWorkspace: (workspaceId) => serviceWorkspaces.ensure(workspaceId),
        promptCosts: () => runtime.promptCosts(),
        contextLimitTokens: runtimeConfig.contextLimitTokens,
        maxOutputTokens: runtimeConfig.maxOutputTokens,
        safetyMarginTokens: runtimeConfig.safetyMarginTokens,
    });
    const runs = new RunService({
        runtime,
        broker,
        sessions,
        workspaces,
        idempotency,
        runsDirectory: join(stateDir, "runs"),
        clock,
        assembler,
        sessionContext,
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
            assembler,
            serviceWorkspaces,
            pdfJobs: new Map(),
            runtimePointers: options.runtimePointers,
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
