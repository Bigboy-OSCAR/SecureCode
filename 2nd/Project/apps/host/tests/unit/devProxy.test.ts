/**
 * Same-origin access through a dev proxy configured like scripts/dev/viteProxy.ts
 * (Host rewritten to the target, browser Origin kept): bootstrap cookie, an
 * authenticated JSON route and a streamed SSE response all pass the proxy hop.
 * The proxy is a minimal node:http forwarder, not Vite itself (the UI is 1.1).
 * Also pins the SDK start switches that keep MCP, plugins and agents out.
 */
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { createServer, request as httpRequest, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import type { RunSnapshot, Session, Workspace } from "@securecode/contracts";
import { createViteApiProxy } from "../../../../scripts/dev/viteProxy.js";
import { buildStartInput } from "../../src/cline/adapter/sessionConfig.js";
import { FakeRuntime } from "../support/fakeRuntime.js";
import { ApiClient, startTestHost } from "../support/hostHarness.js";

function startForwarder(target: URL): Promise<Server> {
    const proxy = createServer((incoming, outgoing) => {
        const forwarded = httpRequest(
            {
                host: target.hostname,
                port: target.port,
                method: incoming.method,
                path: incoming.url,
                // changeOrigin: Host becomes the target; Origin and Cookie pass through unchanged.
                headers: { ...incoming.headers, host: target.host },
            },
            (upstream) => {
                outgoing.writeHead(upstream.statusCode ?? 502, upstream.headers);
                upstream.pipe(outgoing);
            },
        );
        incoming.pipe(forwarded);
    });
    return new Promise((resolve) => proxy.listen(0, "127.0.0.1", () => resolve(proxy)));
}

it("serves bootstrap, cookie-authenticated JSON and SSE through the same-origin dev proxy", async () => {
    const runtime = new FakeRuntime();
    const test = await startTestHost({ runtimeFactory: async () => runtime, transformer: null, gate: null });
    const entry = createViteApiProxy(Number(new URL(test.baseUrl).port))["/api"];
    assert.deepEqual([entry.changeOrigin, entry.ws], [true, false]);
    const proxy = await startForwarder(new URL(entry.target));
    const uiOrigin = `http://127.0.0.1:${(proxy.address() as AddressInfo).port}`;
    try {
        const browser = new ApiClient(uiOrigin);
        assert.equal((await browser.bootstrap()).status, 403, "an origin the host does not allow is refused");
        test.allowedOrigins.push(uiOrigin);
        assert.equal((await browser.bootstrap()).status, 200);
        assert.equal((await browser.send("GET", "/api/v1/settings")).status, 200);
        const root = mkdtempSync(join(tmpdir(), "securecode-proxy-ws-"));
        const workspace = (
            await browser.send("POST", "/api/v1/workspaces", {
                display_name: "p",
                root_path: root,
                idempotency_key: "proxy-ws-key",
            })
        ).body as Workspace;
        const session = (
            await browser.send("POST", "/api/v1/sessions", {
                workspace_id: workspace.workspace_id,
                idempotency_key: "proxy-session",
            })
        ).body as Session;
        const run = (
            await browser.send("POST", `/api/v1/sessions/${session.session_id}/runs`, {
                prompt: "hi",
                idempotency_key: "proxy-run-key",
            })
        ).body as RunSnapshot;
        await browser.waitFor(run.run_id, (snapshot) => snapshot.status === "running");
        const stream = browser.events(run.run_id);
        await new Promise((resolve) => setTimeout(resolve, 100));
        runtime.listener?.({ kind: "output_delta", messageId: "m", text: "via proxy" });
        runtime.finish({ finish: "completed", text: "" });
        const { events } = await stream;
        assert.ok(events.some((event) => event.type === "run.output_delta"));
        assert.equal(events.at(-1)?.type, "run.status_changed");
    } finally {
        proxy.close();
        await test.close();
    }
});

it("starts SDK sessions with MCP, plugins, spawn agents, teams, checkpoints and compaction off", () => {
    const input = buildStartInput({
        sessionId: "ses_0123456789",
        prompt: "p",
        workspaceRoot: "/w",
        providerId: "anthropic",
        modelId: "claude-sonnet-5-5",
        apiKey: "k",
        baseUrl: null,
        maxOutputTokens: 1024,
        systemPrompt: "system",
        tools: [],
        toolPolicies: {},
        hooks: {},
    });
    const config = input.config;
    assert.deepEqual(
        [
            config.enableTools,
            config.enableSpawnAgent,
            config.enableAgentTeams,
            config.disableMcpSettingsTools,
            config.mcpApps,
            config.yolo,
        ],
        [false, false, false, true, false, false],
    );
    assert.deepEqual(
        [config.hookErrorMode, config.checkpoint?.enabled, config.compaction?.enabled],
        ["throw", false, false],
    );
    assert.deepEqual(input.localRuntime?.configExtensions, []);
    assert.equal(input.interactive, true);
});
