/**
 * Public API contract over the assembled host with a fake runtime: browser
 * bootstrap/cookie auth, origin guard, health/settings, workspaces, sessions,
 * idempotency, body caps and 501 routes left for 3.6.
 */
import assert from "node:assert/strict";
import { mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, describe, it } from "node:test";
import { SCHEMA_REFS, type Session, type Workspace } from "@securecode/contracts";
import { PENDING_ROUTES } from "../../src/routes/pendingRoutes.js";
import { FakeRuntime } from "../support/fakeRuntime.js";
import { startTestHost, validator, type TestHost } from "../support/hostHarness.js";

function errorCode(body: unknown): string {
    assert.ok(validator.validate(SCHEMA_REFS.errorResponse, body).valid, JSON.stringify(body));
    return (body as { error: { code: string } }).error.code;
}

describe("host public API", () => {
    const runtime = new FakeRuntime();
    let test: TestHost;
    const root = mkdtempSync(join(tmpdir(), "securecode-ws-"));

    before(async () => {
        writeFileSync(join(root, "main.py"), "print(1)\n");
        test = await startTestHost({ runtimeFactory: async () => runtime, transformer: null, gate: null });
    });

    after(async () => {
        await test.close();
    });

    it("keeps health minimal and every other route behind the bootstrap cookie", async () => {
        const health = await test.client.send("GET", "/api/v1/health");
        assert.deepEqual(health.body, { schema_version: "1", status: "ok" });
        assert.equal((await test.client.send("GET", "/api/v1/settings")).status, 401);
        assert.equal(errorCode((await test.client.send("GET", "/api/v1/workspaces")).body), "UNAUTHENTICATED");
        const foreign = await test.client.send(
            "POST",
            "/api/v1/auth/bootstrap",
            { code: "x".repeat(20) },
            { origin: "http://evil.test" },
        );
        assert.equal(errorCode(foreign.body), "ORIGIN_REJECTED");
    });

    it("exchanges the one-time code for an HttpOnly SameSite=Strict cookie exactly once", async () => {
        assert.equal(
            errorCode((await test.client.bootstrap("wrong-code-000000000000")).body),
            "BOOTSTRAP_CODE_INVALID",
        );
        const ok = await test.client.bootstrap();
        assert.equal(ok.status, 200);
        assert.ok(validator.validate(SCHEMA_REFS.bootstrapResponse, ok.body).valid);
        const cookie = ok.headers.get("set-cookie") ?? "";
        assert.match(cookie, /HttpOnly/);
        assert.match(cookie, /SameSite=Strict/);
        assert.match(cookie, /Path=\/api/);
        const second = await fetch(`${test.baseUrl}/api/v1/auth/bootstrap`, {
            method: "POST",
            headers: { origin: test.baseUrl, "content-type": "application/json" },
            body: JSON.stringify({ code: "test-launch-code-0123456789" }),
        });
        assert.equal(errorCode(await second.json()), "BOOTSTRAP_CODE_INVALID");
    });

    it("shows components, settings and protections without secrets once authenticated", async () => {
        const health = await test.client.send("GET", "/api/v1/health");
        assert.ok(validator.validate(SCHEMA_REFS.healthResponse, health.body).valid);
        assert.ok((health.body as { components: unknown[] }).components.length > 0);
        const settings = await test.client.send("GET", "/api/v1/settings");
        assert.ok(validator.validate(SCHEMA_REFS.settingsResponse, settings.body).valid, JSON.stringify(settings.body));
        assert.doesNotMatch(JSON.stringify(settings.body), /fixture-not-a-secret|securecode-host-test/);
    });

    it("registers workspace roots idempotently with a separate local display path", async () => {
        const request = { display_name: "demo", root_path: root, idempotency_key: "ws-key-0001" };
        const overlap = await test.client.send("POST", "/api/v1/workspaces", { ...request, root_path: test.dataDir });
        assert.equal(overlap.status, 403);
        assert.equal(
            (overlap.body as { error: { details: { reason: string } } }).error.details.reason,
            "root_overlaps_service_data",
        );
        const created = await test.client.send("POST", "/api/v1/workspaces", request);
        assert.equal(created.status, 201);
        assert.ok(validator.validate(SCHEMA_REFS.workspace, created.body).valid);
        assert.equal((created.body as Workspace).display_path, realpathSync(root));
        assert.equal("root_path" in (created.body as object), false);
        const replay = await test.client.send("POST", "/api/v1/workspaces", request);
        assert.equal((replay.body as Workspace).workspace_id, (created.body as Workspace).workspace_id);
        const conflict = await test.client.send("POST", "/api/v1/workspaces", { ...request, display_name: "other" });
        assert.equal(errorCode(conflict.body), "IDEMPOTENCY_CONFLICT");
        for (const rootPath of ["relative/dir", join(root, "main.py"), join(root, "missing")]) {
            const rejected = await test.client.send("POST", "/api/v1/workspaces", {
                ...request,
                root_path: rootPath,
                idempotency_key: `bad-${rootPath.length}-key`,
            });
            assert.equal(errorCode(rejected.body), "FORBIDDEN");
            assert.ok(!JSON.stringify(rejected.body).includes(root));
        }
        const list = await test.client.send("GET", "/api/v1/workspaces?limit=1");
        assert.ok(validator.validate(SCHEMA_REFS.workspaceListResponse, list.body).valid);
    });

    it("refuses sessions while required hooks are not registered", async () => {
        const workspace = (await test.client.send("GET", "/api/v1/workspaces")).body as { items: Workspace[] };
        const workspaceId = workspace.items[0]?.workspace_id ?? "";
        runtime.ready = false;
        const refused = await test.client.send("POST", "/api/v1/sessions", {
            workspace_id: workspaceId,
            idempotency_key: "ses-key-0001",
        });
        assert.equal(errorCode(refused.body), "PROTECTION_UNAVAILABLE");
        runtime.ready = true;
        const created = await test.client.send("POST", "/api/v1/sessions", {
            workspace_id: workspaceId,
            idempotency_key: "ses-key-0002",
        });
        assert.equal(created.status, 201);
        assert.ok(validator.validate(SCHEMA_REFS.session, created.body).valid);
        const listed = await test.client.send("GET", `/api/v1/workspaces/${workspaceId}/sessions`);
        assert.ok(validator.validate(SCHEMA_REFS.sessionListResponse, listed.body).valid);
        assert.equal((listed.body as { items: Session[] }).items.length, 1);
    });

    it("caps bodies, validates JSON and answers unbuilt routes with 501 and their owner", async () => {
        const huge = await test.client.send(
            "POST",
            "/api/v1/workspaces",
            JSON.stringify({ display_name: "x".repeat(70 * 1024) }),
        );
        assert.equal(errorCode(huge.body), "PAYLOAD_TOO_LARGE");
        const invalid = await test.client.send("POST", "/api/v1/workspaces", { display_name: "x" });
        assert.equal(errorCode(invalid.body), "VALIDATION_FAILED");
        for (const route of PENDING_ROUTES) {
            const path = route.path.replace(/:[a-z_]+/g, "ws_0123456789");
            const response = await test.client.send(route.method, path, route.method === "GET" ? undefined : {});
            assert.equal(response.status, 501, path);
            assert.equal(
                (response.body as { error: { details: { owner_task: string } } }).error.details.owner_task,
                route.ownerTask,
            );
        }
    });
});
