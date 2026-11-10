/**
 * Real-SDK scenario helpers: a host whose runtime is the installed ClineCore
 * talking to the 3.1 scripted Anthropic provider, plus workspace/session/run
 * setup and AppEvent stream checks. Import tools/sdk-probe/src/env/isolated-cline-home.js
 * before this module so the SDK never touches the user's ~/.cline.
 */
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SCHEMA_REFS, type AppEvent, type RunSnapshot, type Session, type Workspace } from "@securecode/contracts";
import type { ScriptedTurn } from "../../../../tools/sdk-probe/src/fixtures/anthropic-sse.js";
import { ScriptedProviderFetch } from "../../../../tools/sdk-probe/src/fixtures/scripted-fetch.js";
import { ClineAgentRuntime } from "../../src/cline/adapter/clineRuntime.js";
import { FixtureGate, FixtureTransformer } from "./fixtureHooks.js";
import { startTestHost, validator, type TestHost } from "./hostHarness.js";

export interface SdkHost extends TestHost {
    provider: ScriptedProviderFetch;
    transformer: FixtureTransformer;
    gate: FixtureGate;
    workspaceRoot: string;
    workspaceId: string;
}

export async function startSdkHost(
    turns: ScriptedTurn[],
    options: {
        approvalTimeoutMs?: number;
        dataDir?: string;
        workspaceRoot?: string;
        initializeWorkspace?: boolean;
    } = {},
): Promise<SdkHost> {
    const provider = new ScriptedProviderFetch(turns);
    const transformer = new FixtureTransformer();
    const gate = new FixtureGate();
    const test = await startTestHost({
        runtimeFactory: (runtimeOptions) => ClineAgentRuntime.create(runtimeOptions),
        transformer,
        gate,
        providerFetch: provider.fetch,
        ...(options.approvalTimeoutMs ? { approvalTimeoutMs: options.approvalTimeoutMs } : {}),
        ...(options.dataDir ? { dataDir: options.dataDir } : {}),
    });
    const workspaceRoot = options.workspaceRoot ?? mkdtempSync(join(tmpdir(), "securecode-sdk-ws-"));
    writeFileSync(join(workspaceRoot, "notes.txt"), "hello from the workspace\n");
    let workspaceId = "";
    if (options.initializeWorkspace !== false) {
        await test.client.bootstrap();
        const workspace = await test.client.send("POST", "/api/v1/workspaces", {
            display_name: "sdk",
            root_path: workspaceRoot,
            idempotency_key: "sdk-workspace-key",
        });
        workspaceId = (workspace.body as Workspace).workspace_id;
    }
    return { ...test, provider, transformer, gate, workspaceRoot, workspaceId };
}

export async function createSession(
    host: Pick<SdkHost, "client" | "workspaceId">,
    key = `session-${Date.now()}`,
): Promise<string> {
    const response = await host.client.send("POST", "/api/v1/sessions", {
        workspace_id: host.workspaceId,
        idempotency_key: key,
    });
    assert.equal(response.status, 201, JSON.stringify(response.body));
    return (response.body as Session).session_id;
}

export async function createRun(
    host: Pick<SdkHost, "client">,
    sessionId: string,
    prompt: string,
    key = `run-${Date.now()}-${Math.random()}`,
): Promise<RunSnapshot> {
    const response = await host.client.send("POST", `/api/v1/sessions/${sessionId}/runs`, {
        prompt,
        idempotency_key: key,
    });
    assert.equal(response.status, 201, JSON.stringify(response.body));
    assert.ok(validator.validate(SCHEMA_REFS.runSnapshot, response.body).valid);
    return response.body as RunSnapshot;
}

export function isFinished(snapshot: RunSnapshot): boolean {
    return snapshot.terminal !== null;
}

/** Every event matches the contract, belongs to the run and has sequence 1..n with matching SSE ids. */
export function assertEventStream(events: AppEvent[], ids: (string | null)[], runId: string, firstSequence = 1): void {
    events.forEach((event, index) => {
        const check = validator.validate(SCHEMA_REFS.appEvent, event);
        assert.ok(check.valid, `${event.type}: ${check.errors.join("; ")}`);
        assert.equal(event.run_id, runId);
        assert.equal(event.sequence, firstSequence + index);
        assert.equal(ids[index], String(event.sequence));
    });
}

export function outboundText(host: SdkHost): string {
    return host.provider.capturedRequests.map((request) => request.bodyText).join("\n");
}
