/** Sidebar removal is persistent and reversible, while files and conversation records are preserved. */
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

it("removes a project through the UI client and restores its files and conversations after restart", async () => {
    const root = mkdtempSync(join(tmpdir(), "localdesk-remove-ws-"));
    const dataDir = mkdtempSync(join(tmpdir(), "localdesk-remove-data-"));
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
        const request = { display_name: "removal test", root_path: root, idempotency_key: "remove-create-key" };
        const workspace = await api.createWorkspace(request);
        const session = await api.createSession({
            workspace_id: workspace.workspace_id,
            idempotency_key: "remove-session-key",
        });
        const run = await api.createRun(session.session_id, {
            prompt: "preserved question",
            idempotency_key: "remove-run-key",
        });
        await host.client.waitFor(run.run_id, (value) => value.status === "running");
        runtime.finish({ finish: "completed", text: "preserved answer" });
        await host.client.waitFor(run.run_id, (value) => value.status === "completed");

        assert.equal((await api.deleteWorkspace(workspace.workspace_id)).workspace_id, workspace.workspace_id);
        assert.equal((await api.listWorkspaces()).items.length, 0);
        assert.equal((await host.client.send("GET", `/api/v1/workspaces/${workspace.workspace_id}`)).status, 404);
        assert.equal(
            (await api.deleteWorkspace(workspace.workspace_id)).workspace_id,
            workspace.workspace_id,
            "removal is idempotent",
        );
        await assert.rejects(
            api.createWorkspace(request),
            (error: unknown) => error instanceof ApiClientError && error.status === 404,
        );
        assert.equal(
            (await api.listWorkspaces()).items.length,
            0,
            "replaying an old create cannot restore a removed project",
        );
        assert.equal(
            (
                await host.client.send("POST", "/api/v1/sessions", {
                    workspace_id: workspace.workspace_id,
                    idempotency_key: "removed-session-key",
                })
            ).status,
            404,
        );
        assert.equal(
            (
                await host.client.send("POST", `/api/v1/sessions/${session.session_id}/runs`, {
                    prompt: "must not start",
                    idempotency_key: "removed-run-key",
                })
            ).status,
            404,
        );
        assert.equal(readFileSync(source, "utf8"), "original file\n");

        await host.close();
        host = null;
        host = await startTestHost({
            runtimeFactory: async () => new FakeRuntime(),
            transformer: null,
            gate: null,
            dataDir,
        });
        await host.client.bootstrap();
        const restoredApi = browserApi(host);
        assert.equal((await restoredApi.listWorkspaces()).items.length, 0, "removal survives restart");
        const restored = await restoredApi.createWorkspace({
            ...request,
            display_name: "restored project",
            idempotency_key: "restore-create-key",
        });
        assert.equal(restored.workspace_id, workspace.workspace_id);
        assert.equal(restored.display_name, "restored project");
        assert.deepEqual(
            (await restoredApi.listSessions(workspace.workspace_id)).items.map((value) => value.session_id),
            [session.session_id],
        );
        assert.equal((await restoredApi.getRun(run.run_id)).answer.text, "preserved answer");
        assert.equal(readFileSync(source, "utf8"), "original file\n");
    } finally {
        await host?.close();
        rmSync(root, { recursive: true, force: true });
        rmSync(dataDir, { recursive: true, force: true });
    }
});

it("requires browser authentication and a trusted origin for project removal", async () => {
    const host = await startTestHost({ runtimeFactory: async () => new FakeRuntime(), transformer: null, gate: null });
    try {
        const path = "/api/v1/workspaces/ws_missing0001";
        assert.equal((await host.client.send("DELETE", path)).status, 401);
        await host.client.bootstrap();
        assert.equal(
            (await host.client.send("DELETE", path, undefined, { origin: "https://untrusted.test" })).status,
            403,
        );
        assert.equal((await host.client.send("DELETE", path)).status, 404);
    } finally {
        await host.close();
        rmSync(host.dataDir, { recursive: true, force: true });
    }
});

it("blocks removal during planning and execution without blocking unrelated projects", async () => {
    const root = mkdtempSync(join(tmpdir(), "localdesk-busy-ws-"));
    const otherRoot = mkdtempSync(join(tmpdir(), "localdesk-idle-ws-"));
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
            display_name: "busy",
            root_path: root,
            idempotency_key: "busy-project-key",
        });
        const other = await api.createWorkspace({
            display_name: "idle",
            root_path: otherRoot,
            idempotency_key: "idle-project-key",
        });
        const session = await api.createSession({
            workspace_id: workspace.workspace_id,
            idempotency_key: "busy-session-key",
        });
        const creating = api.createRun(session.session_id, { prompt: "wait", idempotency_key: "busy-create-run" });
        await entered;
        const assertBlocked = async (): Promise<void> => {
            await assert.rejects(api.deleteWorkspace(workspace.workspace_id), (error: unknown) => {
                assert.ok(error instanceof ApiClientError);
                assert.equal(error.status, 409);
                assert.equal(error.details?.reason, "workspace_has_active_run");
                assert.match(error.message, /실행이 끝나거나 취소/);
                return true;
            });
        };
        await assertBlocked();
        assert.equal(
            (await api.getSession(session.session_id)).active_run_id,
            null,
            "the planning phase has no run ID yet",
        );
        await api.deleteWorkspace(other.workspace_id);
        assert.deepEqual(
            (await api.listWorkspaces()).items.map((value) => value.workspace_id),
            [workspace.workspace_id],
        );
        releasePlan();
        const run = await creating;
        await host.client.waitFor(run.run_id, (value) => value.status === "running");
        await assertBlocked();
        runtime.finish({ finish: "completed", text: "done" });
        await host.client.waitFor(run.run_id, (value) => value.status === "completed");
        await api.deleteWorkspace(workspace.workspace_id);
        assert.equal((await api.listWorkspaces()).items.length, 0);
    } finally {
        releasePlan();
        await host.close();
        for (const directory of [root, otherRoot, host.dataDir]) rmSync(directory, { recursive: true, force: true });
    }
});
