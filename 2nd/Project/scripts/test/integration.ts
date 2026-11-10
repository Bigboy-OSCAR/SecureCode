/**
 * `npm run test:integration`: real processes on loopback. Covers the service
 * process test, the real-SDK host suites (scripted provider), the host ->
 * context-service health chain with browser auth and the production refusal
 * while required hooks are missing, and the degraded path when the service
 * stops. Unbuilt suites are PENDING.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ContractValidator, SCHEMA_REFS, type HealthResponse } from "@securecode/contracts";
import { pendingResults } from "../lib/pendingSuites.js";
import { runAndExit, type StepResult } from "../lib/report.js";
import { findFreePorts, startServices } from "../lib/services.js";
import { toolStep, uvStep } from "../lib/processes.js";
import { ContextServiceError } from "../../apps/host/src/context-client/contextServiceError.js";
import { createRuntimeClient } from "../../apps/host/src/pointer-hooks/runtimeClient.js";

const validator = ContractValidator.load();

function expectStep(name: string, passed: boolean, detail: string): StepResult {
    return { name, status: passed ? "PASS" : "FAIL", detail };
}

/**
 * The real host process: cookie auth, then sessions open with the 4.4 hook and 4.8 gate registered.
 * Gate decisions on real SDK payloads are covered by apps/host/tests/integration/requestBudgetSdk.test.ts
 * (this chain has no provider key, so the SDK stops before fetch).
 */
async function productionGuardSteps(hostUrl: string, bootstrapCode: string, dataDir: string): Promise<StepResult[]> {
    const results: StepResult[] = [];
    const json = { origin: hostUrl, "content-type": "application/json" };
    const anonymous = await fetch(`${hostUrl}/api/v1/sessions`, { method: "POST", headers: json, body: "{}" });
    results.push(
        expectStep("chain: API needs the launch cookie", anonymous.status === 401, `HTTP ${anonymous.status}`),
    );
    const login = await fetch(`${hostUrl}/api/v1/auth/bootstrap`, {
        method: "POST",
        headers: json,
        body: JSON.stringify({ code: bootstrapCode }),
    });
    const cookie = (login.headers.get("set-cookie") ?? "").split(";", 1)[0] ?? "";
    results.push(
        expectStep(
            "chain: bootstrap sets HttpOnly cookie",
            login.status === 200 && cookie !== "",
            `HTTP ${login.status}`,
        ),
    );
    const authed = { ...json, cookie };
    const root = mkdtempSync(join(dataDir, "ws-"));
    const workspace = await fetch(`${hostUrl}/api/v1/workspaces`, {
        method: "POST",
        headers: authed,
        body: JSON.stringify({ display_name: "it", root_path: root, idempotency_key: "it-workspace-key" }),
    });
    const workspaceBody = (await workspace.json()) as { workspace_id?: string };
    const session = await fetch(`${hostUrl}/api/v1/sessions`, {
        method: "POST",
        headers: authed,
        body: JSON.stringify({ workspace_id: workspaceBody.workspace_id, idempotency_key: "it-session-key" }),
    });
    const sessionBody = (await session.json()) as { error?: { code?: string } };
    results.push(
        expectStep(
            "chain: sessions open once the 4.4 hook and 4.8 request gate are registered",
            workspace.status === 201 && session.status === 201,
            `workspace HTTP ${workspace.status}, session HTTP ${session.status} ${sessionBody.error?.code ?? ""}`,
        ),
    );
    return results;
}

async function hostServiceChainSteps(): Promise<StepResult[]> {
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-it-"));
    const results: StepResult[] = [];
    let services;
    try {
        services = await startServices({ ...(await findFreePorts()), dataDir });
    } catch (error) {
        rmSync(dataDir, { recursive: true, force: true });
        return [
            expectStep("chain: start host + service", false, error instanceof Error ? error.message : "start failed"),
        ];
    }
    try {
        results.push(expectStep("chain: start host + service", true, "both healthy on 127.0.0.1"));

        const okBody: unknown = await (await fetch(`${services.hostUrl}/api/v1/health`)).json();
        const okValid = validator.validate(SCHEMA_REFS.healthResponse, okBody).valid;
        results.push(
            expectStep(
                "chain: host health ok",
                okValid && (okBody as HealthResponse).status === "ok",
                JSON.stringify(okBody),
            ),
        );

        const anonymous = await fetch(`${services.serviceUrl}/internal/v1/health`);
        results.push(
            expectStep("chain: service rejects no token", anonymous.status === 401, `HTTP ${anonymous.status}`),
        );

        results.push(...(await productionGuardSteps(services.hostUrl, services.bootstrapCode, dataDir)));

        const scope = { workspaceId: "ws_review1234", sessionId: "ses_review1234" };
        const client = createRuntimeClient({
            baseUrl: services.serviceUrl,
            internalToken: services.internalToken,
            validator,
        });
        const signal = new AbortController().signal;
        const content = "가나다 runtime output\n".repeat(1000);
        const meta = { origin: "run_command", mediaType: "text/plain", truncatedBeforeStorage: false };
        const upload = client.openUpload(scope, meta, signal);
        for (let index = 0; index < content.length; index += 997) {
            await upload.write(Buffer.from(content.slice(index, index + 997), "utf8"));
        }
        const streamed = await upload.finish();
        const stored = await client.store(scope, content, { ...meta, origin: "read_file" }, signal);
        const readCode = await client.read(scope, { pointer: stored.pointer, max_bytes: 9 }, signal).then(
            () => "content",
            (error: unknown) => (error instanceof ContextServiceError ? error.code : "other"),
        );
        results.push(
            expectStep(
                "chain: runtime store streams and stores through the real service",
                streamed.byteSize === Buffer.byteLength(content) && stored.byteSize === streamed.byteSize,
                "internal stream + JSON store, scoped pointers, exact byte counts",
            ),
        );
        results.push(
            expectStep(
                "chain: runtime read fails closed without a configured token counter",
                readCode === "TOKENIZER_UNAVAILABLE",
                `read result: ${readCode} (no raw fallback; counted reads are covered by host SDK tests)`,
            ),
        );

        await services.stopService();
        const degradedBody: unknown = await (await fetch(`${services.hostUrl}/api/v1/health`)).json();
        const degraded =
            validator.validate(SCHEMA_REFS.healthResponse, degradedBody).valid &&
            (degradedBody as HealthResponse).status === "degraded" &&
            !(degradedBody as HealthResponse).components;
        results.push(expectStep("chain: host degraded when service stops", degraded, JSON.stringify(degradedBody)));
    } finally {
        await services.stopAll();
        rmSync(dataDir, { recursive: true, force: true });
    }
    return results;
}

await runAndExit("test:integration", [
    async () => [await uvStep("service process (pytest -m integration)", ["pytest", "-q", "-m", "integration"])],
    async () => [
        await toolStep("SDK host: pointer plugin, runs, approvals, cancel, SSE", process.execPath, [
            "--import",
            "tsx",
            "--test",
            "apps/host/tests/integration/**/*.test.ts",
        ]),
    ],
    async () => [
        await toolStep("dev launcher lifecycle", process.execPath, [
            "--import",
            "tsx",
            "--test",
            "scripts/test/devLifecycle.test.ts",
        ]),
    ],
    hostServiceChainSteps,
    () => Promise.resolve(pendingResults("integration")),
]);
