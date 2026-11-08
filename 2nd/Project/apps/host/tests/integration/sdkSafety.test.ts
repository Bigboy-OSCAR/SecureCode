/**
 * Installed @cline/sdk + scripted provider: hook failure/timeout and gate
 * refusal fail closed, large tool output is replaced before the model sees it,
 * SSE resumes after Last-Event-ID, sessions stay isolated with one active run
 * each, idempotent run creation, and no checkpoint touches the Git repository.
 */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import type { RunSnapshot } from "@securecode/contracts";
import {
    assertEventStream,
    createRun,
    createSession,
    isFinished,
    outboundText,
    startSdkHost,
} from "../support/sdkScenario.js";

const SENTINEL = "SECURECODE_HOST_SENTINEL_9C2E";
const readTurn = (path: string) => ({
    toolUses: [{ toolUseId: "toolu_read", toolName: "read_file", input: { path } }],
});

it("fails the run closed when the tool result transformer fails or hangs", async () => {
    for (const mode of ["fail", "hang"] as const) {
        const host = await startSdkHost([readTurn("big.txt"), { text: "must not be reached" }]);
        try {
            writeFileSync(join(host.workspaceRoot, "big.txt"), `${SENTINEL}\n`.repeat(400));
            host.transformer.mode = mode;
            const run = await createRun(host, await createSession(host), "read big.txt");
            const done = await host.client.waitFor(run.run_id, isFinished);
            assert.equal(done.status, "failed", mode);
            assert.equal(done.terminal?.reason_code, "SERVICE_UNAVAILABLE");
            assert.equal(host.provider.capturedRequests.length, 1, "no request after the failed hook");
            assert.doesNotMatch(outboundText(host), new RegExp(SENTINEL));
        } finally {
            await host.close();
        }
    }
});

it("never sends a request the model request gate refuses or cannot decide", async () => {
    for (const [mode, code] of [
        ["block", "BUDGET_EXCEEDED"],
        ["throw", "TOKENIZER_UNAVAILABLE"],
    ] as const) {
        const host = await startSdkHost([{ text: "unused" }]);
        try {
            host.gate.mode = mode;
            const run = await createRun(host, await createSession(host), "hello");
            const done = await host.client.waitFor(run.run_id, isFinished);
            assert.equal(done.status, "failed");
            assert.equal(done.terminal?.reason_code, code);
            assert.equal(host.provider.capturedRequests.length, 0);
            assert.equal(host.gate.requests.length, 1);
        } finally {
            await host.close();
        }
    }
});

it("replaces large tool output with a runtime pointer before the next model request", async () => {
    const host = await startSdkHost([readTurn("big.txt"), { text: "summarised" }]);
    try {
        writeFileSync(join(host.workspaceRoot, "big.txt"), `${SENTINEL} line\n`.repeat(600));
        const run = await createRun(host, await createSession(host), "read big.txt");
        const { events, ids } = await host.client.events(run.run_id);
        assertEventStream(events, ids, run.run_id);
        const created = events.find((event) => event.type === "run.pointer_created");
        assert.ok(created && created.type === "run.pointer_created");
        assert.ok(created.payload.byte_size > 4096);
        assert.equal(host.provider.capturedRequests.length, 2);
        assert.doesNotMatch(host.provider.capturedRequests[1]?.bodyText ?? "", new RegExp(SENTINEL));
        assert.match(host.provider.capturedRequests[1]?.bodyText ?? "", /securecode:\/\/runtime\//);
        assert.doesNotMatch(JSON.stringify(events), new RegExp(SENTINEL));
        const snapshot = await host.client.snapshot(run.run_id);
        assert.equal(snapshot.tool_calls[0]?.output_pointer, created.payload.pointer);
        assert.doesNotMatch(JSON.stringify(snapshot), new RegExp(SENTINEL));
    } finally {
        await host.close();
    }
});

it("resumes SSE after Last-Event-ID and keeps two sessions isolated with one active run each", async () => {
    const host = await startSdkHost([
        { toolUses: [{ toolUseId: "toolu_wa", toolName: "write_file", input: { path: "a.txt", content: "A" } }] },
        { text: "B done" },
        { text: "A done" },
    ]);
    try {
        const sessionA = await createSession(host, "session-a-key");
        const sessionB = await createSession(host, "session-b-key");
        const runA = await createRun(host, sessionA, "write a", "run-a-key-0001");
        const waiting = await host.client.waitFor(runA.run_id, (snapshot) => snapshot.pending_approvals.length > 0);
        const busy = await host.client.send("POST", `/api/v1/sessions/${sessionA}/runs`, {
            prompt: "again",
            idempotency_key: "run-a-key-0002",
        });
        const busyError = (
            busy.body as { error: { code: string; retryable: boolean; details: { active_run_id: string } } }
        ).error;
        assert.deepEqual(
            [busy.status, busyError.code, busyError.retryable, busyError.details.active_run_id],
            [409, "RUN_ALREADY_ACTIVE", true, runA.run_id],
        );
        const replay = await host.client.send("POST", `/api/v1/sessions/${sessionA}/runs`, {
            prompt: "write a",
            idempotency_key: "run-a-key-0001",
        });
        assert.deepEqual([replay.status, (replay.body as RunSnapshot).run_id], [200, runA.run_id]);
        const conflict = await host.client.send("POST", `/api/v1/sessions/${sessionA}/runs`, {
            prompt: "other",
            idempotency_key: "run-a-key-0001",
        });
        assert.equal((conflict.body as { error: { code: string } }).error.code, "IDEMPOTENCY_CONFLICT");

        const liveA = host.client.events(runA.run_id);
        const runB = await createRun(host, sessionB, "say B");
        assert.equal((await host.client.waitFor(runB.run_id, isFinished)).status, "completed");
        const approval = waiting.pending_approvals[0];
        assert.ok(approval);
        await host.client.send("POST", `/api/v1/runs/${runA.run_id}/approvals/${approval.approval_id}`, {
            decision: "approve",
            input_digest: approval.input_digest,
        });
        const streamA = await liveA;
        assertEventStream(streamA.events, streamA.ids, runA.run_id);
        assert.ok(streamA.events.every((event) => event.session_id === sessionA));
        const doneA = await host.client.snapshot(runA.run_id);
        assert.equal(doneA.answer.text, "A done");

        const resumed = await host.client.events(runA.run_id, 3);
        assertEventStream(resumed.events, resumed.ids, runA.run_id, 4);
        assert.deepEqual(resumed.events, streamA.events.slice(3));
        assert.deepEqual((await host.client.events(runA.run_id, doneA.replay.last_sequence)).events, []);
    } finally {
        await host.close();
    }
});

it("does not create checkpoints or touch Git state while a run writes files", async () => {
    const workspaceRoot = mkdtempSync(join(tmpdir(), "securecode-git-ws-"));
    execFileSync("git", ["init", "-q"], { cwd: workspaceRoot });
    const gitState = (): string =>
        [["for-each-ref"], ["stash", "list"]]
            .map((args) => execFileSync("git", args, { cwd: workspaceRoot, encoding: "utf8" }))
            .join("|");
    const before = gitState();
    const host = await startSdkHost(
        [
            { toolUses: [{ toolUseId: "toolu_w", toolName: "write_file", input: { path: "new.txt", content: "x" } }] },
            { text: "done" },
        ],
        { workspaceRoot },
    );
    try {
        const run = await createRun(host, await createSession(host), "write");
        const approval = (await host.client.waitFor(run.run_id, (s) => s.pending_approvals.length > 0))
            .pending_approvals[0];
        assert.ok(approval);
        await host.client.send("POST", `/api/v1/runs/${run.run_id}/approvals/${approval.approval_id}`, {
            decision: "approve",
            input_digest: approval.input_digest,
        });
        assert.equal((await host.client.waitFor(run.run_id, isFinished)).status, "completed");
        assert.equal(gitState(), before);
    } finally {
        await host.close();
    }
});
