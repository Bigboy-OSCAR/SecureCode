/**
 * [fixture provider] Exercises the UI HTTP/SSE clients against the actual host
 * and installed Cline SDK. The scripted provider is not a live provider run.
 */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { it } from "node:test";
import { ApiClientError } from "../../../ui/src/api/apiErrors.js";
import type { ApiFetch } from "../../../ui/src/api/httpClient.js";
import { ApiHttpClient } from "../../../ui/src/api/httpClient.js";
import { HttpRunClient } from "../../../ui/src/api/httpRunClient.js";
import { SseClient } from "../../../ui/src/api/events/sseClient.js";
import { createIdempotencyKey } from "../../../ui/src/api/runClient.js";
import { RunController } from "../../../ui/src/features/chat/model/runController.js";
import type { AppEvent, RunSnapshot } from "@securecode/contracts";
import { isFinished, startSdkHost } from "../support/sdkScenario.js";

const toolUse = (id: string, name: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName: name, input }],
});

it("connects UI clients to real Cline SDK lifecycle with a scripted provider fixture", async () => {
    const host = await startSdkHost(
        [
            { text: "Reading.", ...toolUse("toolu_ui_read", "read_file", { path: "notes.txt" }) },
            { text: "The file says hello." },
            toolUse("toolu_ui_reject", "write_file", { path: "out/rejected.txt", content: "must not be written" }),
            { text: "The write was rejected." },
            toolUse("toolu_ui_cancel", "run_command", { command: "echo should-not-run > cancelled.txt" }),
            { text: "unused after cancellation" },
        ],
        { initializeWorkspace: false },
    );
    let controller: RunController | null = null;
    try {
        let cookie = "";
        let disconnectFirstEvent = true;
        const eventCursors: string[] = [];
        const apiFetch: ApiFetch = async (input, init) => {
            const headers = new Headers(init?.headers);
            headers.set("origin", host.baseUrl);
            if (cookie) {
                headers.set("cookie", cookie);
            }
            const url = input instanceof Request ? input.url : input instanceof URL ? input.href : input;
            const response = await fetch(url, { ...init, headers });
            if (url.endsWith("/auth/bootstrap")) {
                cookie = (response.headers.get("set-cookie") ?? "").split(";", 1)[0] ?? "";
            }
            if (url.endsWith("/events")) {
                eventCursors.push(headers.get("last-event-id") ?? "");
                if (disconnectFirstEvent) {
                    disconnectFirstEvent = false;
                    const firstEvent = await readFirstDataEvent(response);
                    return new Response(firstEvent, {
                        status: response.status,
                        headers: { "content-type": "text/event-stream; charset=utf-8" },
                    });
                }
            }
            return response;
        };
        const api = new ApiHttpClient(`${host.baseUrl}/api/v1`, apiFetch);
        const runClient = new HttpRunClient(api, new SseClient(`${host.baseUrl}/api/v1`, apiFetch, 1));

        await api.bootstrap({ code: "test-launch-code-0123456789" });
        assert.ok((await api.getSettings()).schema_version === "1");
        assert.equal((await api.listWorkspaces()).items.length, 0);
        const workspaceRequest = {
            display_name: "UI SDK fixture",
            root_path: host.workspaceRoot,
            idempotency_key: createIdempotencyKey(),
        };
        const workspace = await api.createWorkspace(workspaceRequest);
        const duplicateWorkspace = await api.createWorkspace(workspaceRequest);
        assert.equal(duplicateWorkspace.workspace_id, workspace.workspace_id);
        assert.notEqual(workspace.workspace_id, "");
        const sessionRequest = {
            workspace_id: workspace.workspace_id,
            idempotency_key: createIdempotencyKey(),
        };
        const session = await api.createSession(sessionRequest);
        const duplicateSession = await api.createSession(sessionRequest);
        assert.equal(duplicateSession.session_id, session.session_id);

        const firstRequest = {
            prompt: "Read notes.txt and summarize it.",
            idempotency_key: createIdempotencyKey(),
        };
        const run = await runClient.createRun(session.session_id, firstRequest);
        const duplicateRun = await runClient.createRun(session.session_id, firstRequest);
        assert.equal(duplicateRun.run_id, run.run_id);
        const events = await collectUntilTerminal(runClient, run.run_id, 0);
        assert.ok(events.some((event) => event.type === "run.output_delta"));
        assert.ok(events.some((event) => event.type === "run.tool_call_updated"));
        assert.deepEqual(
            events.map((event) => event.sequence),
            events.map((_event, index) => index + 1),
        );
        assert.deepEqual(eventCursors, ["0", "1"], "reconnect must resume after the last delivered event");
        const completed = await api.getRun(run.run_id);
        assert.equal(completed.status, "completed");
        assert.match(completed.answer.text, /file says hello/);
        assert.equal(host.provider.capturedRequests.length, 2, "duplicate create must not execute a second SDK run");
        assert.deepEqual(await api.getRun(run.run_id), completed);

        controller = new RunController(runClient, session.session_id, workspace.workspace_id);
        assert.equal(await controller.createRun("Write a file."), true);
        const rejectionRun = controller.getSnapshot().snapshot;
        assert.ok(rejectionRun);
        const pending = await waitForController(controller, (snapshot) => snapshot.pending_approvals.length > 0);
        const approval = pending.pending_approvals[0];
        assert.ok(approval);
        assert.equal(await controller.decideApproval(approval.approval_id, "reject"), true);
        const rejected = await waitForController(controller, isFinished);
        assert.equal(rejected.approval_history?.[0]?.status, "rejected");
        assert.equal(existsSync(`${host.workspaceRoot}/out/rejected.txt`), false);

        assert.equal(await controller.createRun("Run a command."), true);
        await waitForController(controller, (snapshot) => snapshot.pending_approvals.length > 0);
        assert.equal(await controller.cancelRun(), true);
        const cancelled = await waitForController(controller, isFinished);
        assert.equal(cancelled.status, "cancelled");
        assert.equal(host.provider.capturedRequests.length, 5, "cancel must stop the pending scripted SDK turn");
    } finally {
        controller?.dispose();
        await host.close();
    }
});

async function collectUntilTerminal(
    client: HttpRunClient,
    runId: RunSnapshot["run_id"],
    after: number,
): Promise<AppEvent[]> {
    return new Promise<AppEvent[]>((resolve, reject) => {
        const events: AppEvent[] = [];
        let lastDisconnect: Error | undefined;
        let stop = (): void => undefined;
        const timeout = setTimeout(() => {
            stop();
            reject(lastDisconnect ?? new Error("Timed out waiting for the UI event stream."));
        }, 15000);
        stop = client.subscribe(
            runId,
            after,
            (event) => {
                events.push(event);
                if (event.type === "run.status_changed" && event.payload.terminal) {
                    clearTimeout(timeout);
                    stop();
                    resolve(events);
                }
            },
            (error) => {
                if (error) {
                    if (
                        error instanceof ApiClientError &&
                        (error.kind === "network" || error.kind === "server" || error.kind === "timeout")
                    ) {
                        lastDisconnect = error;
                    } else {
                        clearTimeout(timeout);
                        reject(error);
                    }
                }
            },
        );
    });
}

async function readFirstDataEvent(response: Response): Promise<string> {
    if (!response.body) {
        throw new Error("The host did not return an SSE body.");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
        while (true) {
            const result = await reader.read();
            if (result.done) {
                throw new Error("The host stream ended before its first event.");
            }
            if (!(result.value instanceof Uint8Array)) {
                throw new Error("The host returned an invalid SSE data chunk.");
            }
            buffer += decoder.decode(result.value, { stream: true });
            let boundary = /\r?\n\r?\n/.exec(buffer);
            while (boundary) {
                const block = buffer.slice(0, boundary.index);
                const eventBlock = `${block}${boundary[0]}`;
                buffer = buffer.slice(boundary.index + boundary[0].length);
                if (block.split(/\r?\n/).some((line) => line.startsWith("data:"))) {
                    await reader.cancel();
                    return eventBlock;
                }
                boundary = /\r?\n\r?\n/.exec(buffer);
            }
        }
    } finally {
        reader.releaseLock();
    }
}

async function waitForController(
    controller: RunController,
    predicate: (snapshot: RunSnapshot) => boolean,
): Promise<RunSnapshot> {
    const deadline = Date.now() + 15000;
    while (Date.now() <= deadline) {
        const snapshot = controller.getSnapshot().snapshot;
        if (snapshot && predicate(snapshot)) {
            return snapshot;
        }
        await new Promise((resolve) => setTimeout(resolve, 25));
    }
    throw new Error("Timed out waiting for the UI run snapshot.");
}
