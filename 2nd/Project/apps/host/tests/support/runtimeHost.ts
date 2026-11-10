/**
 * [test] Real Runtime Pointer stack for 4.4 SDK tests: the actual context-service app (tests/support/
 * counted_service.py: production app + deterministic token counter) on loopback, the 4.4 client and
 * transformer, the installed ClineCore with the 3.1 scripted provider, and leak scanners for the
 * provider payloads, SSE events and on-disk state (host data + SDK session store).
 * Import tools/sdk-probe/src/support/isolated-cline-home.js before this module.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { delimiter, join, resolve } from "node:path";
import { randomBytes } from "node:crypto";
import type { ScriptedTurn } from "../../../../tools/sdk-probe/src/fixtures/anthropic-sse.js";
import { ScriptedProviderFetch } from "../../../../tools/sdk-probe/src/fixtures/scripted-fetch.js";
import { ClineAgentRuntime, type ClineRuntimeOptions } from "../../src/cline/adapter/clineRuntime.js";
import type { ModelRequestGate, RuntimePointerService, ToolResultTransformer } from "../../src/cline/adapter/ports.js";
import { HttpContextServiceClient } from "../../src/context-client/httpContextServiceClient.js";
import { createRuntimeClient } from "../../src/pointer-hooks/runtimeClient.js";
import { createRuntimeToolResultTransformer } from "../../src/pointer-hooks/runtimeToolResultTransformer.js";
import { FixtureGate } from "./fixtureHooks.js";
import { startTestHost, validator, type TestHost, type TestHostOptions } from "./hostHarness.js";

const SERVICE_DIR = resolve(import.meta.dirname, "../../../../services/context-service");
export const POINTER_PLACEHOLDER = "<runtime-pointer>";
const POINTER_URI = /securecode:\/\/runtime\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/[0-9a-f-]{36}\?v=1/;

export interface CountedService {
    url: string;
    token: string;
    dataDir: string;
    stop(): Promise<void>;
}

async function freePort(): Promise<number> {
    const server = createServer();
    await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
    const address = server.address();
    await new Promise<void>((done) => server.close(() => done()));
    if (address === null || typeof address === "string") throw new Error("no free port");
    return address.port;
}

/** Starts the real context-service app with the test token counter; throws if the venv is missing. */
export async function startCountedService(
    extraEnv: Record<string, string> = {},
    existingDataDir?: string,
): Promise<CountedService> {
    const python = join(SERVICE_DIR, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
    if (!existsSync(python)) throw new Error("context-service venv missing: run uv sync in services/context-service");
    const dataDir = existingDataDir ?? mkdtempSync(join(tmpdir(), "securecode-runtime-svc-"));
    const token = randomBytes(24).toString("hex");
    const port = await freePort();
    const env: NodeJS.ProcessEnv = { ...process.env, ANTHROPIC_API_KEY: "" };
    Object.assign(env, {
        SECURECODE_INTERNAL_TOKEN: token,
        SECURECODE_DATA_DIR: dataDir,
        SECURECODE_CONTEXT_SERVICE_HOST: "127.0.0.1",
        SECURECODE_CONTEXT_SERVICE_PORT: String(port),
        PYTHONPATH: [join(SERVICE_DIR, "src"), join(SERVICE_DIR, "tests")].join(delimiter),
        ...extraEnv,
    });
    const child: ChildProcess = spawn(python, ["-m", "support.counted_service"], {
        cwd: SERVICE_DIR,
        env,
        stdio: "ignore",
        windowsHide: true,
    });
    const url = `http://127.0.0.1:${port}`;
    const closed = new Promise<void>((done) => child.once("close", () => done()));
    const stop = async (): Promise<void> => {
        if (child.exitCode === null && child.signalCode === null) child.kill();
        await closed;
    };
    for (let attempt = 0; attempt < 100; attempt += 1) {
        try {
            const response = await fetch(`${url}/internal/v1/health`, {
                headers: { authorization: `Bearer ${token}` },
                signal: AbortSignal.timeout(500),
            });
            if (response.ok) return { url, token, dataDir, stop };
        } catch {
            // not listening yet
        }
        await new Promise((done) => setTimeout(done, 100));
    }
    await stop();
    throw new Error("counted context-service did not start");
}

export interface RuntimeHost extends TestHost {
    service: CountedService;
    client: TestHost["client"];
    runtimeClient: RuntimePointerService;
    provider: ScriptedProviderFetch;
    workspaceId: string;
    workspaceRoot: string;
}

/** Fills POINTER_PLACEHOLDER inputs of later scripted tool calls with the last pointer the model saw. */
function fillingFetch(provider: ScriptedProviderFetch, turns: ScriptedTurn[]): typeof fetch {
    return async (input, init) => {
        const body = typeof init?.body === "string" ? init.body : "";
        const seen = body.match(new RegExp(POINTER_URI.source, "g"));
        const pointer = seen?.at(-1);
        if (pointer) {
            for (const turn of turns) {
                for (const use of turn.toolUses ?? []) {
                    if (use.input.pointer === POINTER_PLACEHOLDER) use.input.pointer = pointer;
                }
            }
        }
        return provider.fetch(input, init);
    };
}

export async function startRuntimeHost(
    turns: ScriptedTurn[],
    options: {
        wrapClient?: (client: RuntimePointerService) => RuntimePointerService;
        runtime?: Partial<Pick<ClineRuntimeOptions, "maxCapturedBytes" | "pointerThresholdBytes">>;
        transformer?: (client: RuntimePointerService) => ToolResultTransformer;
        /** Request gate built against the started service (default: the 3.5 fixture gate). */
        gate?: (service: CountedService) => ModelRequestGate;
        serviceEnv?: Record<string, string>;
        /** System prompt as production builds it (e.g. with the PDF skill). */
        systemPrompt?: string;
        provider?: TestHostOptions["provider"];
        /** Replaces the scripted Anthropic provider (e.g. an OpenAI-compatible stream). */
        providerFetch?: typeof fetch;
    } = {},
): Promise<RuntimeHost> {
    const service = await startCountedService(options.serviceEnv);
    const realClient = createRuntimeClient({ baseUrl: service.url, internalToken: service.token, validator });
    const runtimeClient = options.wrapClient ? options.wrapClient(realClient) : realClient;
    const provider = new ScriptedProviderFetch(turns);
    const test = await startTestHost({
        runtimeFactory: (runtimeOptions) => ClineAgentRuntime.create({ ...runtimeOptions, ...options.runtime }),
        transformer: (options.transformer ?? createRuntimeToolResultTransformer)(runtimeClient),
        gate: options.gate ? options.gate(service) : new FixtureGate(),
        runtimePointers: runtimeClient,
        providerFetch: options.providerFetch ?? fillingFetch(provider, turns),
        contextClient: new HttpContextServiceClient({ baseUrl: service.url, internalToken: service.token, validator }),
        ...(options.systemPrompt ? { systemPrompt: options.systemPrompt } : {}),
        ...(options.provider ? { provider: options.provider } : {}),
    });
    const workspaceRoot = mkdtempSync(join(tmpdir(), "securecode-rt-ws-"));
    writeFileSync(join(workspaceRoot, "notes.txt"), "hello\n");
    await test.client.bootstrap();
    const workspace = await test.client.send("POST", "/api/v1/workspaces", {
        display_name: "runtime",
        root_path: workspaceRoot,
        idempotency_key: "runtime-workspace",
    });
    const workspaceId = (workspace.body as { workspace_id: string }).workspace_id;
    return {
        ...test,
        service,
        runtimeClient: realClient,
        provider,
        workspaceId,
        workspaceRoot,
        close: async () => {
            await test.close();
            await service.stop();
        },
    };
}

/** Concatenated text of every file under the given roots (host state, SDK session store). */
export function scanFiles(...roots: string[]): string {
    const parts: string[] = [];
    const walk = (path: string): void => {
        if (!existsSync(path)) return;
        if (statSync(path).isDirectory()) {
            for (const name of readdirSync(path)) walk(join(path, name));
        } else {
            parts.push(readFileSync(path).toString("latin1"));
        }
    };
    for (const root of roots) walk(root);
    return parts.join("\n");
}

export function outbound(provider: ScriptedProviderFetch): string {
    return provider.capturedRequests.map((request) => request.bodyText).join("\n");
}
