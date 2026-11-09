/**
 * Installed @cline/sdk + scripted provider through the public API: a run that
 * reads a file and answers, approval reject/approve/expiry, cancel while an
 * approval waits (late decisions refused) and refused git commit/push.
 */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { it } from "node:test";
import { SCHEMA_REFS, type ApprovalDecisionResponse, type RunSnapshot } from "@securecode/contracts";
import { validator } from "../support/hostHarness.js";
import {
    assertEventStream,
    createRun,
    createSession,
    isFinished,
    outboundText,
    startSdkHost,
} from "../support/sdkScenario.js";

const toolUse = (id: string, name: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName: name, input }],
});

async function waitForApproval(host: Awaited<ReturnType<typeof startSdkHost>>, runId: string): Promise<RunSnapshot> {
    return host.client.waitFor(runId, (snapshot) => snapshot.pending_approvals.length > 0 || isFinished(snapshot));
}

it("completes a run that reads a workspace file, streaming contract events", async () => {
    const host = await startSdkHost([
        { text: "Reading.", ...toolUse("toolu_read", "read_file", { path: "notes.txt" }) },
        { text: "The file says hello." },
    ]);
    try {
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "What does notes.txt say?");
        const { events, ids } = await host.client.events(run.run_id);
        assertEventStream(events, ids, run.run_id);
        const statuses = events
            .filter((event) => event.type === "run.status_changed")
            .map((event) => event.payload.status);
        assert.deepEqual(statuses, ["queued", "running", "completed"]);
        const snapshot = await host.client.snapshot(run.run_id);
        assert.ok(validator.validate(SCHEMA_REFS.runSnapshot, snapshot).valid);
        assert.equal(snapshot.answer.text, "Reading.The file says hello.");
        assert.equal(snapshot.tool_calls[0]?.phase, "completed");
        assert.equal(snapshot.replay.last_sequence, events.at(-1)?.sequence);
        const firstTools = (host.provider.capturedRequests[0]?.body.tools as { name: string }[])
            .map((tool) => tool.name)
            .sort();
        assert.deepEqual(firstTools, [
            "list_files",
            "read_file",
            "run_command",
            "runtime_read",
            "runtime_search",
            "write_file",
        ]);
        assert.match(outboundText(host), /hello from the workspace/);
        assert.equal(host.transformer.inputs.length, 1);
        const session = await host.client.send("GET", `/api/v1/sessions/${sessionId}`);
        assert.equal((session.body as { active_run_id: string | null }).active_run_id, null);
    } finally {
        await host.close();
    }
});

it("rejects and approves file writes by approval id and digest, refusing late decisions", async () => {
    const host = await startSdkHost([
        toolUse("toolu_w1", "write_file", { path: "out/a.txt", content: "first" }),
        { text: "rejected, ok" },
        toolUse("toolu_w2", "write_file", { path: "out/b.txt", content: "second" }),
        { text: "written" },
    ]);
    try {
        const sessionId = await createSession(host);
        const first = await createRun(host, sessionId, "write a");
        const waiting = await waitForApproval(host, first.run_id);
        assert.equal(waiting.status, "awaiting_approval");
        const approval = waiting.pending_approvals[0];
        assert.ok(approval && approval.review.kind === "file_change" && approval.review.content === "first");
        const path = `/api/v1/runs/${first.run_id}/approvals/${approval.approval_id}`;
        const mismatch = await host.client.send("POST", path, {
            decision: "approve",
            input_digest: `sha256:${"0".repeat(64)}`,
        });
        assert.equal((mismatch.body as { error: { code: string } }).error.code, "APPROVAL_DIGEST_MISMATCH");
        const rejected = await host.client.send("POST", path, {
            decision: "reject",
            input_digest: approval.input_digest,
        });
        assert.ok(validator.validate(SCHEMA_REFS.approvalDecisionResponse, rejected.body).valid);
        assert.equal((rejected.body as ApprovalDecisionResponse).approval.status, "rejected");
        const late = await host.client.send("POST", path, { decision: "approve", input_digest: approval.input_digest });
        assert.equal((late.body as { error: { code: string } }).error.code, "APPROVAL_ALREADY_DECIDED");
        const done = await host.client.waitFor(first.run_id, isFinished);
        assert.equal(done.status, "completed");
        assert.equal(done.tool_calls[0]?.phase, "rejected");
        assert.equal(done.approval_history?.[0]?.status, "rejected");
        assert.equal(existsSync(join(host.workspaceRoot, "out", "a.txt")), false);

        const second = await createRun(host, sessionId, "write b");
        const pending = (await waitForApproval(host, second.run_id)).pending_approvals[0];
        assert.ok(pending);
        const approved = await host.client.send(
            "POST",
            `/api/v1/runs/${second.run_id}/approvals/${pending.approval_id}`,
            {
                decision: "approve",
                input_digest: pending.input_digest,
            },
        );
        assert.equal(approved.status, 200);
        assert.equal((await host.client.waitFor(second.run_id, isFinished)).status, "completed");
        assert.equal(readFileSync(join(host.workspaceRoot, "out", "b.txt"), "utf8"), "second");
    } finally {
        await host.close();
    }
});

it("expires an unanswered approval without running the tool", async () => {
    const host = await startSdkHost(
        [toolUse("toolu_cmd", "run_command", { command: "echo should-not-run > ran.txt" }), { text: "gave up" }],
        { approvalTimeoutMs: 300 },
    );
    try {
        const run = await createRun(host, await createSession(host), "run it");
        const pending = (await waitForApproval(host, run.run_id)).pending_approvals[0];
        assert.ok(pending && pending.review.kind === "command");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.approval_history?.[0]?.status, "expired");
        const late = await host.client.send("POST", `/api/v1/runs/${run.run_id}/approvals/${pending.approval_id}`, {
            decision: "approve",
            input_digest: pending.input_digest,
        });
        assert.equal((late.body as { error: { code: string } }).error.code, "APPROVAL_EXPIRED");
        assert.equal(existsSync(join(host.workspaceRoot, "ran.txt")), false);
    } finally {
        await host.close();
    }
});

it("cancels a run while an approval waits; the late approval is refused and nothing runs", async () => {
    const host = await startSdkHost([
        toolUse("toolu_cmd", "run_command", { command: "echo ran > ran.txt" }),
        { text: "unused" },
    ]);
    try {
        const run = await createRun(host, await createSession(host), "run a command");
        const pending = (await waitForApproval(host, run.run_id)).pending_approvals[0];
        assert.ok(pending);
        const cancelling = await host.client.send("POST", `/api/v1/runs/${run.run_id}/cancel`);
        assert.ok(["cancelling", "cancelled"].includes((cancelling.body as RunSnapshot).status));
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "cancelled");
        assert.equal(done.terminal?.status, "cancelled");
        assert.equal(done.approval_history?.[0]?.status, "cancelled");
        const late = await host.client.send("POST", `/api/v1/runs/${run.run_id}/approvals/${pending.approval_id}`, {
            decision: "approve",
            input_digest: pending.input_digest,
        });
        assert.equal((late.body as { error: { code: string } }).error.code, "APPROVAL_ALREADY_DECIDED");
        await new Promise((resolve) => setTimeout(resolve, 200));
        assert.equal(existsSync(join(host.workspaceRoot, "ran.txt")), false);
        assert.equal(host.provider.capturedRequests.length, 1, "no model call after cancel");
        const { events, ids } = await host.client.events(run.run_id);
        assertEventStream(events, ids, run.run_id);
        assert.equal(events.at(-1)?.type, "run.status_changed");
    } finally {
        await host.close();
    }
});

it("refuses git commit and push before asking the user", async () => {
    const commit = ["git", "commit", "-am", "x"].join(" ");
    const push = ["git", "-C", ".", "push"].join(" ");
    const host = await startSdkHost([
        toolUse("toolu_git1", "run_command", { command: commit }),
        toolUse("toolu_git2", "run_command", { command: `echo ok && ${push}` }),
        { text: "not allowed" },
    ]);
    try {
        const run = await createRun(host, await createSession(host), "commit and push");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "completed");
        assert.equal(done.approval_history?.length ?? 0, 0);
        assert.deepEqual(
            done.tool_calls.map((call) => [call.tool_call_id, call.phase]),
            [
                ["toolu_git1", "failed"],
                ["toolu_git2", "failed"],
            ],
        );
        assert.match(done.tool_calls[0]?.summary ?? "", /refused/);
    } finally {
        await host.close();
    }
});
