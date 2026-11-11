/** Conversation removal preserves records for undo and does not affect sibling chats or project files. */
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import { ApiHttpClient } from "../../../ui/src/api/httpClient.js";
import { ApiClientError } from "../../../ui/src/api/apiErrors.js";
import { FakeRuntime } from "../support/fakeRuntime.js";
import { createFixtureContextClient, startTestHost, type TestHost } from "../support/hostHarness.js";

function browserApi(host: TestHost): ApiHttpClient {
    return new ApiHttpClient(`${host.baseUrl}/api/v1`, (input, init) => {
        const headers = new Headers(init?.headers);
        headers.set("origin", host.baseUrl);
        headers.set("cookie", host.client.cookie);
        return fetch(input, { ...init, headers });
    });
}

it("persists conversation deletion across restart and restores the same history without touching siblings", async () => {
    const root = mkdtempSync(join(tmpdir(), "localdesk-remove-chat-"));
    const dataDir = mkdtempSync(join(tmpdir(), "localdesk-chat-data-"));
    const source = join(root, "keep.txt");
    writeFileSync(source, "original file\n");
    const runtime = new FakeRuntime();
    let host: TestHost | null = await startTestHost({
        runtimeFactory: async () => runtime,
        transformer: null,
        gate: null,
        dataDir,
    });
    try {
        await host.client.bootstrap();
        const api = browserApi(host);
        const workspace = await api.createWorkspace({
            display_name: "chat removal",
            root_path: root,
            idempotency_key: "chat-project-key",
        });
        const request = { workspace_id: workspace.workspace_id, idempotency_key: "chat-session-key" };
        const session = await api.createSession(request);
        const sibling = await api.createSession({ ...request, idempotency_key: "chat-sibling-key" });
        const run = await api.createRun(session.session_id, {
            prompt: "preserved question",
            idempotency_key: "chat-run-key",
        });
        await host.client.waitFor(run.run_id, (value) => value.status === "running");
        runtime.finish({ finish: "completed", text: "preserved answer" });
        await host.client.waitFor(run.run_id, (value) => value.status === "completed");

        assert.equal((await api.deleteSession(session.session_id)).session_id, session.session_id);
        assert.equal(
            (await api.deleteSession(session.session_id)).session_id,
            session.session_id,
            "delete is idempotent",
        );
        assert.deepEqual(
            (await api.listSessions(workspace.workspace_id)).items.map((value) => value.session_id),
            [sibling.session_id],
        );
        assert.equal((await api.listWorkspaces()).items[0]?.workspace_id, workspace.workspace_id);
        assert.equal(readFileSync(source, "utf8"), "original file\n");
        for (const operation of [
            () => api.getSession(session.session_id),
            () => api.listRuns(session.session_id),
            () => api.createSession(request),
            () => api.createRun(session.session_id, { prompt: "must not run", idempotency_key: "deleted-chat-run" }),
        ]) {
            await assert.rejects(
                operation(),
                (error: unknown) => error instanceof ApiClientError && error.status === 404,
            );
        }
        await host.close();
        host = null;
        host = await startTestHost({
            runtimeFactory: async () => new FakeRuntime(),
            transformer: null,
            gate: null,
            dataDir,
        });
        await host.client.bootstrap();
        const reopened = browserApi(host);
        assert.deepEqual(
            (await reopened.listSessions(workspace.workspace_id)).items.map((value) => value.session_id),
            [sibling.session_id],
        );
        assert.equal((await reopened.restoreSession(session.session_id)).session_id, session.session_id);
        assert.equal(
            (await reopened.restoreSession(session.session_id)).session_id,
            session.session_id,
            "restore is idempotent",
        );
        assert.equal((await reopened.listSessions(workspace.workspace_id)).items.length, 2);
        assert.equal((await reopened.listRuns(session.session_id)).items[0]?.run_id, run.run_id);
        assert.equal((await reopened.getRun(run.run_id)).answer.text, "preserved answer");
        assert.equal((await reopened.getSession(sibling.session_id)).session_id, sibling.session_id);
        assert.equal(readFileSync(source, "utf8"), "original file\n");

        await reopened.deleteSession(session.session_id);
        await reopened.deleteWorkspace(workspace.workspace_id);
        await assert.rejects(
            reopened.restoreSession(session.session_id),
            (error: unknown) => error instanceof ApiClientError && error.status === 404,
        );
        await reopened.createWorkspace({
            display_name: "restored project",
            root_path: root,
            idempotency_key: "chat-project-restore",
        });
        assert.deepEqual(
            (await reopened.listSessions(workspace.workspace_id)).items.map((value) => value.session_id),
            [sibling.session_id],
            "project restoration does not revive a separately deleted chat",
        );
    } finally {
        await host?.close();
        rmSync(root, { recursive: true, force: true });
        rmSync(dataDir, { recursive: true, force: true });
    }
});

it("protects delete and restore with browser authentication and trusted Origin", async () => {
    const host = await startTestHost({ runtimeFactory: async () => new FakeRuntime(), transformer: null, gate: null });
    try {
        const routes = [
            ["DELETE", "/api/v1/sessions/ses_missing001"],
            ["POST", "/api/v1/sessions/ses_missing001/restore"],
        ] as const;
        for (const [method, path] of routes) assert.equal((await host.client.send(method, path)).status, 401);
        await host.client.bootstrap();
        for (const [method, path] of routes) {
            assert.equal(
                (await host.client.send(method, path, undefined, { origin: "https://untrusted.test" })).status,
                403,
            );
            assert.equal((await host.client.send(method, path)).status, 404);
        }
    } finally {
        await host.close();
        rmSync(host.dataDir, { recursive: true, force: true });
    }
});

it("blocks only the conversation that is planning or running, not idle siblings in the same project", async () => {
    const root = mkdtempSync(join(tmpdir(), "localdesk-busy-chat-"));
    let releasePlan = (): void => {};
    let enteredPlan = (): void => {};
    const held = new Promise<void>((resolve) => {
        releasePlan = resolve;
    });
    const entered = new Promise<void>((resolve) => {
        enteredPlan = resolve;
    });
    const fixture = createFixtureContextClient();
    const runtime = new FakeRuntime();
    const host = await startTestHost({
        runtimeFactory: async () => runtime,
        transformer: null,
        gate: null,
        contextClient: {
            ...fixture,
            context: {
                select: async (request, signal) => {
                    enteredPlan();
                    await held;
                    return fixture.context.select(request, signal);
                },
            },
        },
    });
    try {
        await host.client.bootstrap();
        const api = browserApi(host);
        const workspace = await api.createWorkspace({
            display_name: "busy chat",
            root_path: root,
            idempotency_key: "busy-chat-project",
        });
        const session = await api.createSession({
            workspace_id: workspace.workspace_id,
            idempotency_key: "busy-chat-session",
        });
        const idle = await api.createSession({
            workspace_id: workspace.workspace_id,
            idempotency_key: "idle-chat-session",
        });
        const creating = api.createRun(session.session_id, { prompt: "wait", idempotency_key: "busy-chat-run" });
        await entered;
        const assertBlocked = async (): Promise<void> => {
            await assert.rejects(api.deleteSession(session.session_id), (error: unknown) => {
                assert.ok(error instanceof ApiClientError);
                assert.equal(error.status, 409);
                assert.equal(error.details?.reason, "session_has_active_run");
                assert.match(error.message, /이 대화의 실행이 끝나거나 취소/);
                return true;
            });
        };
        await assertBlocked();
        assert.equal(
            (await api.getSession(session.session_id)).active_run_id,
            null,
            "planning has no active run ID yet",
        );
        await api.deleteSession(idle.session_id);
        await api.restoreSession(idle.session_id);
        releasePlan();
        const run = await creating;
        await host.client.waitFor(run.run_id, (value) => value.status === "running");
        await assertBlocked();
        await api.deleteSession(idle.session_id);
        runtime.finish({ finish: "completed", text: "done" });
        await host.client.waitFor(run.run_id, (value) => value.status === "completed");
        await api.deleteSession(session.session_id);
        assert.equal((await api.listSessions(workspace.workspace_id)).items.length, 0);
    } finally {
        releasePlan();
        await host.close();
        for (const directory of [root, host.dataDir]) rmSync(directory, { recursive: true, force: true });
    }
});
