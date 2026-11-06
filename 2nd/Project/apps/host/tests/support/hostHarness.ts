/**
 * Starts a fully assembled host on an ephemeral loopback port with an
 * injectable runtime factory and fixture hooks, plus a browser-like API
 * client (same-origin header, session cookie, SSE reader). Test-only.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AddressInfo } from "node:net";
import { ContractValidator, type AppEvent, type RunSnapshot, type ServiceHealthResponse } from "@securecode/contracts";
import { assembleHost, type AssembledHost, type HostAssemblyOptions } from "../../src/app/hostAssembly.js";
import type { HostConfig } from "../../src/config/hostConfig.js";
import type { RuntimeConfig } from "../../src/config/runtimeConfig.js";
import type { ContextServiceClient } from "../../src/context-client/ports.js";
import { createLogger } from "../../src/logging/logger.js";
import { Redactor } from "../../src/logging/redaction.js";

export const validator = ContractValidator.load();

export const fakeContextClient = {
    health: () =>
        Promise.resolve<ServiceHealthResponse>({
            schema_version: "1",
            service: "context-service",
            status: "ok",
            version: "0.1.0",
            components: [
                { name: "token_counter", status: "ok" },
                { name: "data_dir", status: "ok" },
            ],
        }),
} as unknown as ContextServiceClient;

export interface TestHostOptions {
    runtimeFactory: HostAssemblyOptions["runtimeFactory"];
    transformer: HostAssemblyOptions["transformer"];
    gate: HostAssemblyOptions["gate"];
    providerFetch?: typeof fetch;
    dataDir?: string;
    approvalTimeoutMs?: number;
    allowedWorkspaceRoots?: string[];
    apiKey?: string | null;
}

export interface TestHost {
    baseUrl: string;
    dataDir: string;
    host: AssembledHost;
    client: ApiClient;
    /** Live origin allow list (like SECURECODE_UI_DEV_PORT adds the Vite origin in hostConfig). */
    allowedOrigins: string[];
    close(): Promise<void>;
}

export async function startTestHost(options: TestHostOptions): Promise<TestHost> {
    const dataDir = options.dataDir ?? mkdtempSync(join(tmpdir(), "securecode-host-test-"));
    const hostConfig: HostConfig = {
        host: "127.0.0.1",
        port: 0,
        contextServiceUrl: "http://127.0.0.1:1",
        internalToken: "t".repeat(40),
        dataDir,
        allowedOrigins: [],
        allowedHosts: [],
        logLevel: "error",
        providerId: "anthropic",
        modelId: "claude-sonnet-5-5",
        providerConfigured: true,
    };
    const runtimeConfig: RuntimeConfig = {
        clineHome: join(dataDir, "cline"),
        approvalTimeoutMs: options.approvalTimeoutMs ?? 10000,
        hookTimeoutMs: 500,
        contextLimitTokens: 200000,
        maxOutputTokens: 1024,
        safetyMarginTokens: 2048,
        providerBaseUrl: null,
        bootstrapCode: "test-launch-code-0123456789",
        allowedWorkspaceRoots: options.allowedWorkspaceRoots ?? [],
        commandTimeoutMs: 5000,
    };
    const host = await assembleHost({
        hostConfig,
        runtimeConfig,
        credentials: { apiKey: options.apiKey === undefined ? "fixture-not-a-secret" : options.apiKey },
        contextClient: fakeContextClient,
        validator,
        logger: createLogger("error", new Redactor(), () => undefined),
        runtimeFactory: options.runtimeFactory,
        transformer: options.transformer,
        gate: options.gate,
        ...(options.providerFetch ? { providerFetch: options.providerFetch } : {}),
        sseKeepAliveMs: 200,
    });
    await new Promise<void>((resolve) => host.server.listen(0, "127.0.0.1", resolve));
    const port = (host.server.address() as AddressInfo).port;
    const baseUrl = `http://127.0.0.1:${port}`;
    hostConfig.allowedOrigins.push(baseUrl);
    hostConfig.allowedHosts.push(`127.0.0.1:${port}`);
    return {
        baseUrl,
        dataDir,
        host,
        client: new ApiClient(baseUrl),
        allowedOrigins: hostConfig.allowedOrigins,
        close: () => host.shutdown(),
    };
}

export interface ApiResponse {
    status: number;
    body: unknown;
    headers: Headers;
}

export class ApiClient {
    cookie = "";

    constructor(readonly baseUrl: string) {}

    async bootstrap(code = "test-launch-code-0123456789"): Promise<ApiResponse> {
        const response = await this.send("POST", "/api/v1/auth/bootstrap", { code });
        const setCookie = response.headers.get("set-cookie") ?? "";
        if (response.status === 200) this.cookie = setCookie.split(";", 1)[0] ?? "";
        return response;
    }

    async send(
        method: string,
        path: string,
        body?: unknown,
        extraHeaders: Record<string, string> = {},
    ): Promise<ApiResponse> {
        const response = await fetch(this.baseUrl + path, {
            method,
            headers: {
                origin: this.baseUrl,
                ...(this.cookie ? { cookie: this.cookie } : {}),
                ...(body === undefined ? {} : { "content-type": "application/json" }),
                ...extraHeaders,
            },
            ...(body === undefined ? {} : { body: typeof body === "string" ? body : JSON.stringify(body) }),
        });
        const text = await response.text();
        return {
            status: response.status,
            body: text ? (JSON.parse(text) as unknown) : null,
            headers: response.headers,
        };
    }

    async snapshot(runId: string): Promise<RunSnapshot> {
        return (await this.send("GET", `/api/v1/runs/${runId}`)).body as RunSnapshot;
    }

    async waitFor(
        runId: string,
        predicate: (snapshot: RunSnapshot) => boolean,
        timeoutMs = 15000,
    ): Promise<RunSnapshot> {
        const deadline = Date.now() + timeoutMs;
        for (;;) {
            const snapshot = await this.snapshot(runId);
            if (predicate(snapshot)) return snapshot;
            if (Date.now() > deadline) throw new Error(`run ${runId} stuck at ${snapshot.status}`);
            await new Promise((resolve) => setTimeout(resolve, 25));
        }
    }

    /** Reads the SSE stream until the server ends it (terminal event or replay gap). */
    async events(
        runId: string,
        lastEventId?: number,
        maxMs = 15000,
    ): Promise<{ events: AppEvent[]; ids: (string | null)[] }> {
        const response = await fetch(`${this.baseUrl}/api/v1/runs/${runId}/events`, {
            headers: {
                cookie: this.cookie,
                ...(lastEventId === undefined ? {} : { "last-event-id": String(lastEventId) }),
            },
            signal: AbortSignal.timeout(maxMs),
        });
        if (response.status !== 200) throw new Error(`SSE status ${response.status}`);
        const text = await response.text();
        const events: AppEvent[] = [];
        const ids: (string | null)[] = [];
        for (const block of text.split("\n\n")) {
            const data = block.split("\n").find((line) => line.startsWith("data: "));
            if (!data) continue;
            events.push(JSON.parse(data.slice(6)) as AppEvent);
            ids.push(
                block
                    .split("\n")
                    .find((line) => line.startsWith("id: "))
                    ?.slice(4) ?? null,
            );
        }
        return { events, ids };
    }
}
