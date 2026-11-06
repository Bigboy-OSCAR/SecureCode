/**
 * Run lifecycle with a fake runtime: terminal status is final, late facts are
 * dropped, a host restart marks interrupted runs failed (idempotency survives),
 * and an SSE request past the replay window gets stream.replay_unavailable.
 */
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import { SCHEMA_REFS, type RunSnapshot, type Session, type Workspace } from "@securecode/contracts";
import { RunEventLog, REPLAY_MAX_EVENTS } from "../../src/routes/runs/eventLog.js";
import { FakeRuntime } from "../support/fakeRuntime.js";
import { startTestHost, validator, type TestHost } from "../support/hostHarness.js";

async function setup(test: TestHost, root: string): Promise<{ sessionId: string; run: RunSnapshot }> {
    await test.client.bootstrap();
    const workspace = await test.client.send("POST", "/api/v1/workspaces", {
        display_name: "w",
        root_path: root,
        idempotency_key: "life-ws-key",
    });
    const session = await test.client.send("POST", "/api/v1/sessions", {
        workspace_id: (workspace.body as Workspace).workspace_id,
        idempotency_key: "life-session-key",
    });
    const sessionId = (session.body as Session).session_id;
    const run = await test.client.send("POST", `/api/v1/sessions/${sessionId}/runs`, {
        prompt: "hi",
        idempotency_key: "life-run-key-1",
    });
    return { sessionId, run: run.body as RunSnapshot };
}

it("keeps a terminal status final and drops late runtime facts", async () => {
    const runtime = new FakeRuntime();
    const test = await startTestHost({ runtimeFactory: async () => runtime, transformer: null, gate: null });
    try {
        const { run } = await setup(test, mkdtempSync(join(tmpdir(), "securecode-life-")));
        await test.client.waitFor(run.run_id, (snapshot) => snapshot.status === "running");
        const listener = runtime.listener;
        assert.ok(listener);
        listener({ kind: "output_delta", messageId: "m1", text: "x".repeat(5000) });
        runtime.finish({ finish: "completed", text: "" });
        const done = await test.client.waitFor(run.run_id, (snapshot) => snapshot.terminal !== null);
        listener({ kind: "output_delta", messageId: "m1", text: "late" });
        const after = await test.client.snapshot(run.run_id);
        assert.equal(after.status, "completed");
        assert.equal(after.answer.text.length, 5000);
        assert.equal(after.replay.last_sequence, done.replay.last_sequence);
        const { events } = await test.client.events(run.run_id);
        const deltas = events.filter((event) => event.type === "run.output_delta");
        assert.deepEqual(
            deltas.map((event) => (event.payload as { text: string }).text.length),
            [4096, 904],
        );
        const cancel = await test.client.send("POST", `/api/v1/runs/${run.run_id}/cancel`);
        assert.equal((cancel.body as RunSnapshot).status, "completed");
    } finally {
        await test.close();
    }
});

it("marks runs interrupted by a host restart as failed and keeps idempotency keys", async () => {
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-restart-"));
    const root = mkdtempSync(join(tmpdir(), "securecode-restart-ws-"));
    const first = await startTestHost({
        runtimeFactory: async () => new FakeRuntime(),
        transformer: null,
        gate: null,
        dataDir,
    });
    const { sessionId, run } = await setup(first, root);
    await first.client.waitFor(run.run_id, (snapshot) => snapshot.status === "running");
    // Simulate a crash: the second host loads the same data while the first never finished the run.
    const second = await startTestHost({
        runtimeFactory: async () => new FakeRuntime(),
        transformer: null,
        gate: null,
        dataDir,
    });
    try {
        await second.client.bootstrap();
        const recovered = await second.client.snapshot(run.run_id);
        assert.ok(validator.validate(SCHEMA_REFS.runSnapshot, recovered).valid);
        assert.equal(recovered.status, "failed");
        assert.equal(recovered.terminal?.reason_code, "SERVICE_UNAVAILABLE");
        const session = (await second.client.send("GET", `/api/v1/sessions/${sessionId}`)).body as Session;
        assert.equal(session.active_run_id, null);
        assert.equal(session.last_run_id, run.run_id);
        const replay = await second.client.send("POST", `/api/v1/sessions/${sessionId}/runs`, {
            prompt: "hi",
            idempotency_key: "life-run-key-1",
        });
        assert.deepEqual([replay.status, (replay.body as RunSnapshot).run_id], [200, run.run_id]);
        const stream = await second.client.events(run.run_id, 0);
        assert.equal(stream.events.length, 1);
        assert.equal(stream.events[0]?.type, "stream.replay_unavailable");
        assert.equal(stream.ids[0], null);
        assert.ok(validator.validate(SCHEMA_REFS.appEvent, stream.events[0]).valid);
    } finally {
        await second.close();
        await first.close();
    }
});

it("bounds the replay window and reports a gap for older Last-Event-ID values", () => {
    const log = new RunEventLog(
        { workspace_id: "ws_0123456789", session_id: "ses_0123456789", run_id: "run_0123456789" },
        () => 0,
    );
    for (let index = 0; index < REPLAY_MAX_EVENTS + 5; index += 1) {
        log.append("run.output_delta", { message_id: "m", text: String(index) });
    }
    assert.deepEqual(log.window(), { oldest_sequence: 6, last_sequence: REPLAY_MAX_EVENTS + 5 });
    assert.deepEqual(log.replayAfter(2), { kind: "gap", oldest: 6 });
    const replay = log.replayAfter(5);
    assert.equal(replay.kind === "events" ? replay.events[0]?.sequence : -1, 6);
    log.append("run.status_changed", { status: "completed", previous_status: "running" });
    log.close();
    assert.equal(log.append("run.output_delta", { message_id: "m", text: "late" }), null);
});
