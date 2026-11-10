/**
 * 4.4 fail-closed paths on the installed SDK with the real Runtime store: rejected approval, missing
 * hook registration, unreachable store, store failure/timeout in afterTool, executor upload failure,
 * cancellation during a streamed command, and removed / expired / session-ended pointers. In every
 * case the bulk output never reaches the provider, SSE, host state or the SDK session store.
 */
import { probeHomeDir } from "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { it } from "node:test";
import type { RunSnapshot } from "@securecode/contracts";
import { ClineAgentRuntime } from "../../src/cline/adapter/clineRuntime.js";
import type { RuntimePointerService } from "../../src/cline/adapter/ports.js";
import { FixtureGate, FixtureTransformer } from "../support/fixtureHooks.js";
import { startTestHost } from "../support/hostHarness.js";
import { createRun, createSession, isFinished } from "../support/sdkScenario.js";
import {
    outbound,
    POINTER_PLACEHOLDER,
    scanFiles,
    startRuntimeHost,
    type RuntimeHost,
} from "../support/runtimeHost.js";

const SLOW = `let i = 0; const t = setInterval(() => { process.stdout.write("STREAM-SENTINEL-" + i++ + "x".repeat(2000) + "\\n"); }, 5); setTimeout(() => clearInterval(t), 20000);`;
const toolUse = (id: string, name: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName: name, input }],
});

function assertNoLeak(host: RuntimeHost, events: unknown, marker: string): void {
    for (const [where, text] of [
        ["provider", outbound(host.provider)],
        ["sse", JSON.stringify(events)],
        ["host state", scanFiles(host.dataDir)],
        ["sdk history", scanFiles(probeHomeDir)],
    ] as const) {
        assert.ok(!text.includes(marker), `${marker} leaked to ${where}`);
    }
}

async function decide(host: RuntimeHost, runId: string, decision: "approve" | "reject"): Promise<void> {
    const waiting = await host.client.waitFor(runId, (s) => s.pending_approvals.length > 0 || isFinished(s));
    const approval = waiting.pending_approvals[0];
    assert.ok(approval);
    await host.client.send("POST", `/api/v1/runs/${runId}/approvals/${approval.approval_id}`, {
        decision,
        input_digest: approval.input_digest,
    });
}

async function stored(host: RuntimeHost, sessionId: string): Promise<string[]> {
    const response = await fetch(`${host.service.url}/internal/v1/runtime/list`, {
        method: "POST",
        headers: { authorization: `Bearer ${host.service.token}`, "content-type": "application/json" },
        body: JSON.stringify({ workspace_id: host.workspaceId, session_id: sessionId, limit: 100 }),
    });
    return ((await response.json()) as { items: { pointer: string }[] }).items.map((item) => item.pointer);
}

it("does not run or store anything when the command approval is rejected", async () => {
    const host = await startRuntimeHost([
        toolUse("toolu_cmd", "run_command", { command: "node touch.js" }),
        { text: "ok" },
    ]);
    try {
        writeFileSync(join(host.workspaceRoot, "touch.js"), `require("fs").writeFileSync("ran.txt", "x")`);
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "run");
        await decide(host, run.run_id, "reject");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.tool_calls[0]?.phase, "rejected");
        assert.equal(existsSync(join(host.workspaceRoot, "ran.txt")), false);
        assert.deepEqual(await stored(host, sessionId), []);
    } finally {
        await host.close();
    }
});

it("refuses sessions without a registered runtime store and runs when the store is unreachable", async () => {
    const unregistered = await startTestHost({
        runtimeFactory: (options) => ClineAgentRuntime.create(options),
        transformer: new FixtureTransformer(),
        gate: new FixtureGate(),
        runtimePointers: null,
    });
    try {
        await unregistered.client.bootstrap();
        const workspace = await unregistered.client.send("POST", "/api/v1/workspaces", {
            display_name: "unregistered",
            root_path: mkdtempSync(join(tmpdir(), "securecode-unreg-")),
            idempotency_key: "w-unregistered",
        });
        const response = await unregistered.client.send("POST", "/api/v1/sessions", {
            workspace_id: (workspace.body as { workspace_id: string }).workspace_id,
            idempotency_key: "s-unregistered",
        });
        assert.equal((response.body as { error?: { code: string } }).error?.code, "PROTECTION_UNAVAILABLE");
    } finally {
        await unregistered.close();
    }
    const host = await startRuntimeHost([{ text: "never" }]);
    try {
        const sessionId = await createSession(host);
        await host.service.stop();
        // 3.6: run creation plans the context first, so an unreachable service refuses the run up front.
        const refused = await host.client.send("POST", `/api/v1/sessions/${sessionId}/runs`, {
            prompt: "hello",
            idempotency_key: "run-service-down",
        });
        assert.equal(refused.status, 503, JSON.stringify(refused.body));
        assert.equal((refused.body as { error: { code: string } }).error.code, "SERVICE_UNAVAILABLE");
        assert.equal(host.provider.capturedRequests.length, 0, "no model call without the context-service");
    } finally {
        await host.close();
    }
});

for (const mode of ["fails", "hangs"] as const) {
    it(`stops the run without forwarding raw output when the afterTool store ${mode}`, async () => {
        const host = await startRuntimeHost(
            [toolUse("toolu_list", "list_files", { path: "many" }), { text: "unused" }],
            {
                wrapClient: (client): RuntimePointerService => ({
                    ...client,
                    store: () =>
                        mode === "fails" ? Promise.reject(new Error("store down")) : new Promise(() => undefined),
                }),
            },
        );
        try {
            // A large listing is the remaining tool output that goes through the afterTool store.
            mkdirSync(join(host.workspaceRoot, "many"));
            for (let i = 0; i < 300; i += 1)
                writeFileSync(join(host.workspaceRoot, "many", `FILE-SENTINEL-${i}-${"n".repeat(40)}.txt`), "");
            const sessionId = await createSession(host);
            const run = await createRun(host, sessionId, "list the files");
            const done: RunSnapshot = await host.client.waitFor(run.run_id, isFinished);
            assert.equal(done.status, "failed");
            assert.equal(done.terminal?.reason_code, "SERVICE_UNAVAILABLE");
            assert.equal(host.provider.capturedRequests.length, 1, "no model call after the failed hook");
            assertNoLeak(host, (await host.client.events(run.run_id)).events, "FILE-SENTINEL");
        } finally {
            await host.close();
        }
    });
}

it("reports an executor upload failure as a tool error without the output", async () => {
    const host = await startRuntimeHost(
        [toolUse("toolu_cmd", "run_command", { command: "node slow.js" }), { text: "the command failed" }],
        {
            wrapClient: (client): RuntimePointerService => ({
                ...client,
                openUpload: () => ({
                    write: () => Promise.reject(new Error("runtime stream upload failed")),
                    finish: () => Promise.reject(new Error("not finished")),
                    abort: () => undefined,
                }),
            }),
        },
    );
    try {
        writeFileSync(join(host.workspaceRoot, "slow.js"), SLOW);
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "run");
        await decide(host, run.run_id, "approve");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.tool_calls[0]?.phase, "failed");
        assert.match(host.provider.capturedRequests[1]?.bodyText ?? "", /runtime stream upload failed/);
        assertNoLeak(host, (await host.client.events(run.run_id)).events, "STREAM-SENTINEL-10");
        assert.deepEqual(await stored(host, sessionId), []);
    } finally {
        await host.close();
    }
});

it("cancels a streaming command: the partial upload is discarded and nothing leaks", async () => {
    const host = await startRuntimeHost([
        toolUse("toolu_cmd", "run_command", { command: "node slow.js" }),
        { text: "unused" },
    ]);
    try {
        writeFileSync(join(host.workspaceRoot, "slow.js"), SLOW);
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "run");
        await decide(host, run.run_id, "approve");
        await new Promise((resolve) => setTimeout(resolve, 1500));
        await host.client.send("POST", `/api/v1/runs/${run.run_id}/cancel`);
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "cancelled");
        await new Promise((resolve) => setTimeout(resolve, 500));
        assert.deepEqual(await stored(host, sessionId), [], "aborted upload left no object");
        assert.equal(host.provider.capturedRequests.length, 1);
        assertNoLeak(host, (await host.client.events(run.run_id)).events, "STREAM-SENTINEL-");
    } finally {
        await host.close();
    }
});

it("returns coded errors for removed, expired and session-ended pointers instead of content", async () => {
    const host = await startRuntimeHost(
        [
            toolUse("toolu_cmd", "run_command", { command: "node slow.js" }),
            toolUse("toolu_read", "runtime_read", {
                pointer: POINTER_PLACEHOLDER,
                selector: { type: "line", start: 3 },
            }),
            { text: "done" },
        ],
        {
            // The session's outputs are removed between the command turn and the read turn.
            wrapClient: (client): RuntimePointerService => ({
                ...client,
                read: async (scope, request, signal) => {
                    await client.clearSession(scope, signal);
                    return client.read(scope, request, signal);
                },
            }),
        },
    );
    try {
        writeFileSync(join(host.workspaceRoot, "slow.js"), SLOW.replace("20000", "300"));
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "run then read");
        await decide(host, run.run_id, "approve");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "completed");
        assert.equal(done.tool_calls[1]?.phase, "failed");
        const readTurn = host.provider.capturedRequests[2]?.bodyText ?? "";
        assert.match(readTurn, /NOT_FOUND/);
        assert.ok(!readTurn.includes("STREAM-SENTINEL-2"));

        const scope = { workspaceId: host.workspaceId, sessionId };
        const kept = await host.runtimeClient.store(
            scope,
            "x".repeat(5000),
            { origin: "t", mediaType: "text/plain", truncatedBeforeStorage: false },
            AbortSignal.timeout(5000),
        );
        const database = new DatabaseSync(join(host.service.dataDir, "runtime", "runtime.sqlite3"));
        database
            .prepare("UPDATE runtime_pointers SET expires_at = ? WHERE pointer_id = ?")
            .run("2000-01-01T00:00:00+00:00", kept.pointer.split("/").at(-1)?.split("?")[0] ?? "");
        database.close();
        await assert.rejects(host.runtimeClient.read(scope, { pointer: kept.pointer }, AbortSignal.timeout(5000)), {
            code: "EXPIRED",
        });

        const live = await host.runtimeClient.store(
            scope,
            "y".repeat(5000),
            { origin: "t", mediaType: "text/plain", truncatedBeforeStorage: false },
            AbortSignal.timeout(5000),
        );
        await host.host.runtime.closeSession(sessionId);
        await assert.rejects(host.runtimeClient.read(scope, { pointer: live.pointer }, AbortSignal.timeout(5000)), {
            code: "NOT_FOUND",
        });
    } finally {
        await host.close();
    }
});
