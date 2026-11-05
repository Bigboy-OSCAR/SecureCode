/** Exercise the installed Cline session and real afterTool plugin with a scripted provider and loopback store. */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { it } from "node:test";
import {
    createSentinelTool,
    buildSentinelOutput,
    SENTINEL_MARKER,
    SENTINEL_TOOL_NAME,
} from "../../../../tools/sdk-probe/src/fixtures/probe-tools.js";
import { withProbeRun } from "../../../../tools/sdk-probe/src/probe/probe-run.js";
import { buildProbeStartInput } from "../../../../tools/sdk-probe/src/probe/session-config.js";
import { createRuntimePointerPlugin } from "../../src/cline/plugins/runtimePointerPlugin.js";

it("stores a full tool result once and exposes only its descriptor to the provider and history", async () => {
    const id = "11111111-aaaa-4444-bbbb-222222222222";
    const sessionId = "ses_rp-12345678";
    const uri = `securecode://runtime/ws_12345678/${sessionId}/${id}?v=1`;
    const token = "test-token".repeat(4);
    const requests: { authorization?: string | undefined; body: string }[] = [];
    const server = createServer((request, response) => {
        const chunks: Buffer[] = [];
        request.on("data", (chunk: Buffer) => chunks.push(chunk));
        request.on("end", () => {
            requests.push({
                authorization: request.headers.authorization,
                body: Buffer.concat(chunks).toString("utf8"),
            });
            response.end(
                JSON.stringify({
                    pointer_id: id,
                    pointer_uri: uri,
                    byte_size: Buffer.byteLength(buildSentinelOutput()),
                }),
            );
        });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    try {
        const baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
        const plugin = createRuntimePointerPlugin({
            workspaceId: "ws_12345678",
            sessionId,
            baseUrl,
            internalToken: token,
        });
        await withProbeRun(
            {
                name: "host-plugin",
                turns: [
                    { toolUses: [{ toolUseId: "call1", toolName: SENTINEL_TOOL_NAME, input: { label: "large" } }] },
                    { text: "done" },
                ],
            },
            async ({ core, scriptedFetch, workspaceDir }) => {
                const result = await core.start(
                    buildProbeStartInput({
                        cwd: workspaceDir,
                        prompt: "get log",
                        extraTools: [createSentinelTool()],
                        sessionId,
                        extensions: [plugin],
                    }),
                );
                assert.equal(requests.length, 1);
                assert.equal(requests[0]?.authorization, `Bearer ${token}`);
                assert.deepEqual(JSON.parse(requests[0]?.body ?? ""), {
                    workspace_id: "ws_12345678",
                    session_id: sessionId,
                    content: buildSentinelOutput(),
                });
                assert.equal(scriptedFetch.capturedRequests.length, 2);
                for (const body of [
                    scriptedFetch.capturedRequests[1]?.bodyText ?? "",
                    JSON.stringify(await core.readMessages(result.sessionId)),
                ]) {
                    assert.ok(body.includes(uri));
                    assert.ok(!body.includes(SENTINEL_MARKER));
                }
            },
        );
    } finally {
        server.closeAllConnections();
        await new Promise<void>((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
    }
});
