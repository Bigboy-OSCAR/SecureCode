/** Public SDK canonical replay: restart/model replacement must keep user and assistant messages. */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRun, createSession, isFinished, outboundText, startSdkHost } from "../support/sdkScenario.js";

test("recreates the SDK runtime and restores canonical conversation before the next turn", async () => {
    const first = await startSdkHost([{ text: "I will remember 고양이." }]);
    let second: Awaited<ReturnType<typeof startSdkHost>> | undefined;
    try {
        const sessionId = await createSession(first);
        const run = await createRun(first, sessionId, "내 암호는 고양이. 기억해 줘.");
        assert.equal((await first.client.waitFor(run.run_id, isFinished)).status, "completed");
        await first.close();
        second = await startSdkHost([{ text: "고양이" }], {
            dataDir: first.dataDir,
            workspaceRoot: first.workspaceRoot,
        });
        const next = await createRun(second, sessionId, "내 암호는?");
        assert.equal((await second.client.waitFor(next.run_id, isFinished)).status, "completed");
        const request = outboundText(second);
        assert.match(request, /내 암호는 고양이/);
        assert.match(request, /I will remember 고양이/);
        assert.match(request, /내 암호는\?/);
        assert.equal(second.gate.requests.length, 1);
    } finally {
        if (second) await second.close();
        else await first.close();
    }
});
