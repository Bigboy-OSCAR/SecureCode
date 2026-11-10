/**
 * 4.8 on the installed SDK: the production request gate (pointer-hooks/modelRequestGate) sits on
 * ClineCoreOptions.fetch and counts every provider call through the real context-service
 * (tokens.request, test counter: UTF-8 bytes of the request input as sent). Each captured outbound
 * payload must be the exact body that was counted and must fit the window with the output reserve and
 * margin; an overflow on a later turn or a missing exact count stops the call before the provider.
 */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { it } from "node:test";
import type { RunSnapshot } from "@securecode/contracts";
import type { ModelRequestDecision, ModelRequestGate, OutboundModelRequest } from "../../src/cline/adapter/ports.js";
import { HttpContextServiceClient } from "../../src/context-client/httpContextServiceClient.js";
import { appliedMargin, createModelRequestGate } from "../../src/pointer-hooks/modelRequestGate.js";
import { validator } from "../support/hostHarness.js";
import { createRun, createSession, isFinished } from "../support/sdkScenario.js";
import { startRuntimeHost, type CountedService, type RuntimeHost } from "../support/runtimeHost.js";

const LIMIT = 200_000;
const MARGIN = 2048;
const MAX_OUTPUT = 1024; // hostHarness runtimeConfig.maxOutputTokens
const toolUse = (id: string, path: string) => ({
    toolUses: [{ toolUseId: id, toolName: "read_file", input: { path } }],
});

function client(service: CountedService): HttpContextServiceClient {
    return new HttpContextServiceClient({ baseUrl: service.url, internalToken: service.token, validator });
}

interface GateRecord {
    body: string;
    decision: ModelRequestDecision;
}

class RecordingGate implements ModelRequestGate {
    readonly records: GateRecord[] = [];
    constructor(private readonly inner: ModelRequestGate) {}

    async check(request: OutboundModelRequest, signal: AbortSignal): Promise<ModelRequestDecision> {
        const decision = await this.inner.check(request, signal);
        this.records.push({ body: request.body, decision });
        return decision;
    }
}

/** Sizes the window to the first request exactly, so any growth on the next turn must be refused. */
class FirstTurnWindowGate implements ModelRequestGate {
    private inner: ModelRequestGate | null = null;
    constructor(private readonly service: CountedService) {}

    async check(request: OutboundModelRequest, signal: AbortSignal): Promise<ModelRequestDecision> {
        if (this.inner === null) {
            const body = JSON.parse(request.body) as { max_tokens?: number };
            const counted = await client(this.service).tokens.countRequest(
                { schema_version: "1", provider_id: request.providerId, model_id: request.modelId, request: body },
                signal,
            );
            const reserve = Math.max(request.maxOutputTokens, body.max_tokens ?? 0);
            const limit = counted.token_count + reserve + 5000;
            this.inner = createModelRequestGate({
                counter: client(this.service).tokens,
                contextLimitTokens: limit,
                safetyMarginTokens: 5000,
                requireExactCount: false,
            });
        }
        return this.inner.check(request, signal);
    }
}

async function runToEnd(host: RuntimeHost, prompt: string): Promise<RunSnapshot> {
    const sessionId = await createSession(host);
    const run = await createRun(host, sessionId, prompt);
    return host.client.waitFor(run.run_id, isFinished);
}

it("counts every SDK outbound payload as sent and keeps each one inside the window", async () => {
    const holder: { gate?: RecordingGate } = {};
    const host = await startRuntimeHost(
        [toolUse("toolu_r1", "notes.txt"), toolUse("toolu_r2", "notes.txt"), { text: "끝" }],
        {
            gate: (service) => {
                holder.gate = new RecordingGate(
                    createModelRequestGate({
                        counter: client(service).tokens,
                        contextLimitTokens: LIMIT,
                        safetyMarginTokens: MARGIN,
                        requireExactCount: false,
                    }),
                );
                return holder.gate;
            },
        },
    );
    try {
        const done = await runToEnd(host, "notes.txt를 두 번 읽어 주세요 🌏");
        assert.equal(done.status, "completed", JSON.stringify(done.terminal));
        const gate = holder.gate;
        assert.ok(gate);
        const captured = host.provider.capturedRequests;
        assert.equal(captured.length, 3, "three model calls (two tool turns and the answer)");
        assert.equal(gate.records.length, captured.length, "every provider call went through the gate");
        const counter = client(host.service).tokens;
        let previous = 0;
        for (const [index, request] of captured.entries()) {
            const record: GateRecord | undefined = gate.records[index];
            assert.ok(record && record.decision.allow);
            assert.equal(record.body, request.bodyText, "the gate counted the exact outbound body");
            const body = request.body as { max_tokens?: number; tools?: unknown[] };
            const recount = await counter.countRequest({
                schema_version: "1",
                provider_id: "anthropic",
                model_id: "claude-sonnet-5-5",
                request: body,
            });
            assert.equal(recount.token_count, record.decision.countedTokens);
            assert.ok(recount.token_count >= Buffer.byteLength(JSON.stringify(body.tools ?? []), "utf8"));
            const reserve = Math.max(MAX_OUTPUT, body.max_tokens ?? 0);
            const margin = appliedMargin(recount.count_mode, MARGIN, LIMIT);
            assert.ok(recount.token_count + reserve + margin <= LIMIT, `request ${index} fits the window`);
            assert.ok(recount.token_count > previous, "history grows turn by turn and is counted every time");
            previous = recount.token_count;
        }
    } finally {
        await host.close();
    }
});

it("refuses the next turn before the provider once history no longer fits, keeping tool pairs intact", async () => {
    const holder: { gate?: RecordingGate } = {};
    const host = await startRuntimeHost([toolUse("toolu_big", "notes.txt"), { text: "never sent" }], {
        gate: (service) => {
            holder.gate = new RecordingGate(new FirstTurnWindowGate(service));
            return holder.gate;
        },
    });
    try {
        const done = await runToEnd(host, "읽어 주세요");
        assert.equal(done.status, "failed");
        assert.equal(done.terminal?.reason_code, "BUDGET_EXCEEDED");
        assert.equal(host.provider.capturedRequests.length, 1, "the overflowing request never left the process");
        const gate = holder.gate;
        const blocked = gate?.records.at(-1);
        assert.ok(blocked && !blocked.decision.allow);
        assert.ok(blocked.body.includes('"toolu_big"') && blocked.body.includes('"tool_result"'));
        assert.equal(blocked.body.split('"toolu_big"').length - 1, 2, "tool_use and tool_result stay paired");
    } finally {
        await host.close();
    }
});

it("hard-cap mode blocks an estimated count before the provider", async () => {
    const host = await startRuntimeHost([{ text: "never sent" }], {
        gate: (service) =>
            createModelRequestGate({
                counter: client(service).tokens,
                contextLimitTokens: LIMIT,
                safetyMarginTokens: MARGIN,
                requireExactCount: true,
            }),
    });
    try {
        const done = await runToEnd(host, "안녕");
        assert.equal(done.terminal?.reason_code, "TOKENIZER_UNAVAILABLE");
        assert.equal(host.provider.capturedRequests.length, 0);
    } finally {
        await host.close();
    }
});

it("hard-cap mode sends the request when the count is exact", async () => {
    const host = await startRuntimeHost([{ text: "ok" }], {
        serviceEnv: { SECURECODE_TEST_REQUEST_COUNT_MODE: "exact" },
        gate: (service) =>
            createModelRequestGate({
                counter: client(service).tokens,
                contextLimitTokens: LIMIT,
                safetyMarginTokens: MARGIN,
                requireExactCount: true,
            }),
    });
    try {
        const done = await runToEnd(host, "안녕");
        assert.equal(done.status, "completed", JSON.stringify(done.terminal));
        assert.equal(host.provider.capturedRequests.length, 1);
    } finally {
        await host.close();
    }
});

it("context.select round-trips through the host client with contract validation", async () => {
    const host = await startRuntimeHost([{ text: "unused" }]);
    try {
        const sessionId = "ses_00000001";
        const stored = await fetch(`${host.service.url}/internal/v1/runtime/pointers`, {
            method: "POST",
            headers: { authorization: `Bearer ${host.service.token}`, "content-type": "application/json" },
            body: JSON.stringify({
                workspace_id: host.workspaceId,
                session_id: sessionId,
                content: "빌드 로그\n".repeat(50),
            }),
        });
        const pointer = ((await stored.json()) as { pointer_uri: string }).pointer_uri;
        const response = await client(host.service).context.select({
            schema_version: "1",
            input: {
                workspace_id: host.workspaceId,
                session_id: sessionId,
                index_revision: 1,
                prompt: "로그",
                context_refs: [],
            },
            current_task_refs: [{ kind: "runtime", pointer }],
            costs: {
                model_context_limit: LIMIT,
                reserved_output_tokens: MAX_OUTPUT,
                safety_margin_tokens: MARGIN,
                message_overhead_tokens: 0,
                system: "SecureCode",
                tool_schema: "",
                history: [],
            },
        });
        assert.equal(response.run_create_error, null);
        assert.equal(response.plan.fragments.length, 1);
        assert.equal(response.plan.fragments[0]?.content, "빌드 로그\n".repeat(50));
    } finally {
        await host.close();
    }
});
