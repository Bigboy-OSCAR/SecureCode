/**
 * 4.10 pointer lifecycle on the installed SDK with the real context-service (scripted provider): small
 * tool results stay inline, a large command output becomes a Runtime Pointer and is re-read in parts
 * across turns and runs, another session cannot read it, a changed Source file is re-read at its new
 * revision, pointers survive a service restart, and the production system prompt carries the PDF skill
 * with exactly the registered tools. Sentinels never reach provider requests, SSE or the run snapshot.
 */
import { probeHomeDir } from "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { it } from "node:test";
import type { RunSnapshot } from "@securecode/contracts";
import { SYSTEM_PROMPT } from "../../src/cline/adapter/sessionConfig.js";
import { loadPdfPointerSkill, withSkills } from "../../src/cline/skills/pdfPointerSkill.js";
import { createRuntimeClient } from "../../src/pointer-hooks/runtimeClient.js";
import { ClineAgentRuntime } from "../../src/cline/adapter/clineRuntime.js";
import { FixtureGate, FixtureTransformer } from "../support/fixtureHooks.js";
import { startTestHost, validator } from "../support/hostHarness.js";
import { createRun, createSession, isFinished } from "../support/sdkScenario.js";
import {
    POINTER_PLACEHOLDER,
    scanFiles,
    startCountedService,
    startRuntimeHost,
    type RuntimeHost,
} from "../support/runtimeHost.js";

const WORK_ROOT = resolve(import.meta.dirname, "../../../..");
const GEN = `
const lines = [];
for (let i = 1; i <= 8000; i++) lines.push(i === 7000 ? "LIFE-TARGET answer=7" : i === 3000 ? "LIFE-SECOND hint=3" : "LIFE-SENTINEL-" + i + "-" + "q".repeat(30));
process.stdout.write(lines.join("\\n") + "\\n");
`;
const toolUse = (id: string, name: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName: name, input }],
});

async function finish(host: RuntimeHost, runId: string): Promise<RunSnapshot> {
    for (;;) {
        const snapshot = await host.client.waitFor(runId, (s) => s.pending_approvals.length > 0 || isFinished(s));
        const approval = snapshot.pending_approvals[0];
        if (!approval) return snapshot;
        await host.client.send("POST", `/api/v1/runs/${runId}/approvals/${approval.approval_id}`, {
            decision: "approve",
            input_digest: approval.input_digest,
        });
    }
}

it("keeps small results inline, pointers large ones, re-reads parts across runs and blocks other sessions", async () => {
    const foreignRead = toolUse("toolu_foreign", "runtime_read", {
        pointer: "",
        selector: { type: "line", start: 7000 },
    });
    const registration = JSON.parse(readFileSync(join(WORK_ROOT, "skills/pdf-pointer/registration.json"), "utf8")) as {
        prompt_marker: string;
        tools: { name: string }[];
    };
    const host = await startRuntimeHost(
        [
            toolUse("toolu_list", "list_files", { path: "." }),
            toolUse("toolu_cmd", "run_command", { command: "node gen.js" }),
            toolUse("toolu_line", "runtime_read", {
                pointer: POINTER_PLACEHOLDER,
                selector: { type: "line", start: 7000, end: 7000 },
            }),
            toolUse("toolu_data1", "read_file", { path: "data.txt" }),
            { text: "첫 run 끝" },
            toolUse("toolu_line2", "runtime_read", {
                pointer: POINTER_PLACEHOLDER,
                selector: { type: "line", start: 3000, end: 3000 },
            }),
            toolUse("toolu_data2", "read_file", { path: "data.txt" }),
            { text: "둘째 run 끝" },
            foreignRead,
            { text: "다른 세션 끝" },
        ],
        { systemPrompt: withSkills(SYSTEM_PROMPT, [loadPdfPointerSkill(WORK_ROOT)]) },
    );
    try {
        writeFileSync(join(host.workspaceRoot, "gen.js"), GEN);
        writeFileSync(join(host.workspaceRoot, "data.txt"), "DATA-VERSION-1\n");
        const sessionId = await createSession(host);
        const first = await finish(
            host,
            (await createRun(host, sessionId, "목록, 명령, 로그 줄, 데이터를 확인")).run_id,
        );
        assert.equal(first.status, "completed", JSON.stringify(first.terminal));
        const pointer = first.tool_calls.find((call) => call.tool_name === "run_command")?.output_pointer ?? "";
        assert.ok(pointer, "large command output became a pointer");

        writeFileSync(join(host.workspaceRoot, "data.txt"), "DATA-VERSION-2 changed during the session\n");
        const second = await finish(host, (await createRun(host, sessionId, "다른 줄과 바뀐 데이터")).run_id);
        assert.equal(second.status, "completed", JSON.stringify(second.terminal));

        const otherSession = await createSession(host, "session-other-1");
        (foreignRead.toolUses[0] as { input: Record<string, unknown> }).input.pointer = pointer;
        const foreign = await finish(host, (await createRun(host, otherSession, "다른 세션 포인터")).run_id);
        assert.equal(foreign.tool_calls[0]?.phase, "failed", "another session cannot read the pointer");

        const bodies = host.provider.capturedRequests.map((request) => request.bodyText);
        const firstSystem = (JSON.parse(bodies[0] ?? "{}") as { system: { text: string }[] }).system
            .map((p) => p.text)
            .join("");
        assert.ok(firstSystem.includes(registration.prompt_marker), "PDF skill is in the real SDK system prompt");
        const sentTools = (JSON.parse(bodies[0] ?? "{}") as { tools: { name: string }[] }).tools.map(
            (tool) => tool.name,
        );
        for (const tool of registration.tools) assert.ok(sentTools.includes(tool.name), `${tool.name} registered`);

        assert.match(bodies[1] ?? "", /notes\.txt/, "small listing stays inline");
        assert.doesNotMatch(bodies[1] ?? "", /\[runtime pointer\]/);
        assert.match(bodies[2] ?? "", /\[runtime pointer\]/, "large output replaced by a pointer");
        assert.match(bodies[3] ?? "", /LIFE-TARGET answer=7/, "requested line re-read");
        assert.match(bodies[4] ?? "", /DATA-VERSION-1/);
        const secondRun = bodies.slice(5, 8).join("\n");
        assert.match(secondRun, /LIFE-SECOND hint=3/, "another part re-read in a later run");
        assert.match(secondRun, /DATA-VERSION-2/, "changed Source re-read at its new content");
        assert.match(secondRun, /\?v=2/, "the changed file has a new revision");
        const foreignRun = bodies.slice(8).join("\n");
        assert.match(foreignRun, /FORBIDDEN/);
        assert.doesNotMatch(foreignRun, /LIFE-TARGET/);

        const all = bodies.join("\n");
        assert.doesNotMatch(all, /LIFE-SENTINEL-\d{3,}-/, "bulk output never reached the model");
        for (const run of [first, second, foreign]) {
            const { events } = await host.client.events(run.run_id);
            assert.doesNotMatch(JSON.stringify(events), /LIFE-SENTINEL-\d{3,}-|LIFE-TARGET/, "SSE");
            const snapshot = await host.client.send("GET", `/api/v1/runs/${run.run_id}`);
            assert.ok(validator.validate("api/run.schema.json#/definitions/RunSnapshot", snapshot.body).valid);
            assert.doesNotMatch(JSON.stringify(snapshot.body), /LIFE-SENTINEL-\d{3,}-/, "UI run state");
        }
        assert.doesNotMatch(scanFiles(probeHomeDir), /LIFE-SENTINEL-\d{3,}-/, "canonical SDK history");

        await host.service.stop();
        const restarted = await startCountedService({}, host.service.dataDir);
        try {
            const client = createRuntimeClient({ baseUrl: restarted.url, internalToken: restarted.token, validator });
            const again = await client.read(
                { workspaceId: host.workspaceId, sessionId },
                { pointer, selector: { type: "line", start: 7000, end: 7000 } },
                AbortSignal.timeout(10000),
            );
            assert.match(again.content, /LIFE-TARGET answer=7/, "pointer survives a service restart");
        } finally {
            await restarted.stop();
        }
    } finally {
        await host.close();
    }
});

for (const missing of ["gate", "transformer"] as const) {
    it(`refuses sessions on the real SDK runtime when the ${missing} hook is not registered`, async () => {
        const host = await startTestHost({
            runtimeFactory: (options) => ClineAgentRuntime.create(options),
            transformer: missing === "transformer" ? null : new FixtureTransformer(),
            gate: missing === "gate" ? null : new FixtureGate(),
        });
        try {
            await host.client.bootstrap();
            const workspace = await host.client.send("POST", "/api/v1/workspaces", {
                display_name: "unhooked",
                root_path: mkdtempSync(join(tmpdir(), "securecode-unhooked-")),
                idempotency_key: `w-unhooked-${missing}`,
            });
            const session = await host.client.send("POST", "/api/v1/sessions", {
                workspace_id: (workspace.body as { workspace_id: string }).workspace_id,
                idempotency_key: `s-unhooked-${missing}`,
            });
            assert.equal(session.status, 503);
            assert.equal((session.body as { error: { code: string } }).error.code, "PROTECTION_UNAVAILABLE");
        } finally {
            await host.close();
        }
    });
}
