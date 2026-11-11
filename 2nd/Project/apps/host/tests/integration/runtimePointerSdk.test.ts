/**
 * 4.4 on the installed SDK with the real Runtime store: an approved command's output is streamed by
 * the executor, replaced by a pointer before the next model request, then re-read by line, search and
 * byte range over several turns; a large read_file result goes through the afterTool store path.
 * Provider payloads, SSE events, host state and the SDK session store must not hold the bulk output.
 */
import { probeHomeDir } from "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { it } from "node:test";
import type { RunSnapshot } from "@securecode/contracts";
import { createRun, createSession, isFinished } from "../support/sdkScenario.js";
import {
    outbound,
    POINTER_PLACEHOLDER,
    scanFiles,
    startRuntimeHost,
    type RuntimeHost,
} from "../support/runtimeHost.js";

const GENERATOR = `
const lines = [];
for (let i = 1; i <= 6000; i++) {
    if (i <= 200) lines.push("preface line " + i + " padding text");
    else if (i === 4321) lines.push("TARGET-LINE-OK result=42");
    else lines.push("SENTINEL-BULK-" + i + "-" + "x".repeat(40));
}
process.stdout.write(lines.join("\\n") + "\\n");
process.exitCode = 3;
`;

const toolUse = (id: string, name: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName: name, input }],
});

async function approveAndFinish(host: RuntimeHost, runId: string): Promise<RunSnapshot> {
    const waiting = await host.client.waitFor(
        runId,
        (snapshot) => snapshot.pending_approvals.length > 0 || isFinished(snapshot),
    );
    const approval = waiting.pending_approvals[0];
    assert.ok(approval, "command approval requested");
    const decided = await host.client.send("POST", `/api/v1/runs/${runId}/approvals/${approval.approval_id}`, {
        decision: "approve",
        input_digest: approval.input_digest,
    });
    assert.equal(decided.status, 200);
    return host.client.waitFor(runId, isFinished);
}

async function listCount(host: RuntimeHost, sessionId: string): Promise<number> {
    const response = await fetch(`${host.service.url}/internal/v1/runtime/list`, {
        method: "POST",
        headers: { authorization: `Bearer ${host.service.token}`, "content-type": "application/json" },
        body: JSON.stringify({ workspace_id: host.workspaceId, session_id: sessionId, limit: 100 }),
    });
    return ((await response.json()) as { items: unknown[] }).items.length;
}

it("replaces approved command output before the next model call and re-reads only the needed parts", async () => {
    const host = await startRuntimeHost([
        toolUse("toolu_cmd", "run_command", { command: "node gen.js" }),
        toolUse("toolu_line", "runtime_read", {
            pointer: POINTER_PLACEHOLDER,
            selector: { type: "line", start: 4321 },
        }),
        toolUse("toolu_find", "runtime_search", { pointer: POINTER_PLACEHOLDER, query: "TARGET-LINE", limit: 1 }),
        toolUse("toolu_head", "runtime_read", {
            pointer: POINTER_PLACEHOLDER,
            selector: { type: "byte", start: 0, end: 5000 },
        }),
        toolUse("toolu_file", "read_file", { path: "big.txt", start_line: 1, end_line: 1 }),
        { text: "answer: 42" },
    ]);
    try {
        writeFileSync(join(host.workspaceRoot, "gen.js"), GENERATOR);
        writeFileSync(
            join(host.workspaceRoot, "big.txt"),
            `${"file head ".repeat(200)}\nFILE-SENTINEL ${"y".repeat(20000)}`,
        );
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "run the generator and find the result");
        const done = await approveAndFinish(host, run.run_id);
        assert.equal(done.status, "completed", JSON.stringify(done.terminal));
        const command = done.tool_calls.find((call) => call.tool_call_id === "toolu_cmd");
        assert.ok(command?.output_pointer, "command result recorded as a pointer");
        const pointer = command.output_pointer;

        const requests = host.provider.capturedRequests.map((request) => request.bodyText);
        assert.equal(requests.length, 6);
        assert.match(requests[1] ?? "", /\[runtime pointer\]/);
        assert.ok(requests[1]?.includes(pointer));
        assert.match(requests[1] ?? "", /capture: complete/);
        assert.match(requests[1] ?? "", /status: \[run_command: exit code 3\]/);
        assert.match(requests[2] ?? "", /TARGET-LINE-OK result=42/);
        assert.match(requests[3] ?? "", /\\"line\\":4321/);
        assert.match(requests[4] ?? "", /preface line 150/);
        const text = outbound(host.provider);
        assert.ok(!text.includes("SENTINEL-BULK"), "bulk command output never reached the provider");
        assert.ok(!text.includes("FILE-SENTINEL"), "read_file (Source adapter) returned only the requested line");
        assert.match(text, /file head file head/, "the requested line was read");

        const { events } = await host.client.events(run.run_id);
        const sse = JSON.stringify(events);
        assert.ok(!sse.includes("SENTINEL-BULK") && !sse.includes("TARGET-LINE-OK") && !sse.includes("preface line"));
        assert.ok(sse.includes(pointer), "SSE carries only the pointer");

        const sdkHistory = scanFiles(probeHomeDir);
        assert.ok(sdkHistory.includes(pointer), "SDK session store holds the pointer (positive control)");
        assert.ok(sdkHistory.includes("TARGET-LINE-OK"), "explicitly read lines are in history");
        for (const stored of [sdkHistory, scanFiles(host.dataDir)]) {
            assert.ok(!stored.includes("SENTINEL-BULK") && !stored.includes("FILE-SENTINEL"));
        }

        assert.equal(await listCount(host, sessionId), 1, "only the command output was stored; bounded reads were not");
        const publicList = await host.client.send(
            "GET",
            `/api/v1/workspaces/${host.workspaceId}/pointers?kind=runtime&session_id=${sessionId}&limit=20`,
        );
        assert.equal(publicList.status, 200);
        const listed = (publicList.body as { items: { provenance: { run_id?: string } }[] }).items;
        assert.equal(listed.length, 1);
        assert.equal(listed[0]?.provenance.run_id, run.run_id, "the pointer names the run that produced it");
        const scope = { workspaceId: host.workspaceId, sessionId };
        const line = await host.runtimeClient.read(
            scope,
            { pointer, selector: { type: "line", start: 6000 } },
            AbortSignal.timeout(5000),
        );
        assert.match(line.content, /^SENTINEL-BULK-6000-/);
    } finally {
        await host.close();
    }
});

it("records a capped capture exactly in the descriptor and the stored object", async () => {
    const host = await startRuntimeHost(
        [toolUse("toolu_cmd", "run_command", { command: "node gen.js" }), { text: "done" }],
        { runtime: { maxCapturedBytes: 64 * 1024 } },
    );
    try {
        writeFileSync(join(host.workspaceRoot, "gen.js"), GENERATOR);
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "run it");
        const done = await approveAndFinish(host, run.run_id);
        assert.equal(done.status, "completed");
        const pointer = done.tool_calls[0]?.output_pointer;
        assert.ok(pointer);
        const request = host.provider.capturedRequests[1]?.bodyText ?? "";
        const match = /capture: truncated before storage; stored the first (\d+) of (\d+) bytes/.exec(request);
        assert.ok(match, "descriptor states the capture range");
        assert.ok(Number(match[1]) <= 64 * 1024 && Number(match[2]) > 300_000);
        const scope = { workspaceId: host.workspaceId, sessionId };
        const tail = await host.runtimeClient.search(
            scope,
            { pointer, query: "output truncated before storage" },
            AbortSignal.timeout(5000),
        );
        assert.equal(tail.matches.length, 1);
        assert.ok(!outbound(host.provider).includes("SENTINEL-BULK-4000"));
    } finally {
        await host.close();
    }
});
