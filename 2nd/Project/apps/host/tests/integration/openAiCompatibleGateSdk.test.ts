/**
 * Local qwen-2.5 on llama.cpp: the installed SDK with providerId "openai-compatible" sends its requests
 * through the same fetch gate. This checks the real SDK body shape: OpenAI tool definitions pass the
 * tool allow list, every body passes the openai_chat framing allow list of the service (test counter
 * with that framing), and hard-cap mode accepts the count once it is exact. The exact token numbers
 * themselves are checked against a real llama.cpp server by `npm run test:live`.
 */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { it } from "node:test";
import type { ModelRequestDecision, ModelRequestGate, OutboundModelRequest } from "../../src/cline/adapter/ports.js";
import { HttpContextServiceClient } from "../../src/context-client/httpContextServiceClient.js";
import { createModelRequestGate } from "../../src/pointer-hooks/modelRequestGate.js";
import { validator } from "../support/hostHarness.js";
import { createRun, createSession, isFinished } from "../support/sdkScenario.js";
import { startRuntimeHost, type CountedService } from "../support/runtimeHost.js";

const MODEL = "qwen2.5-7b-instruct";
const PROVIDER = { providerId: "openai-compatible", modelId: MODEL, baseUrl: "http://127.0.0.1:8080/v1" };

function chunk(delta: Record<string, unknown>, finish: string | null, usage = false): string {
    const body = {
        id: "chatcmpl-1",
        object: "chat.completion.chunk",
        created: 1,
        model: MODEL,
        choices: [{ index: 0, delta, finish_reason: finish }],
        ...(usage ? { usage: { prompt_tokens: 10, completion_tokens: 1, total_tokens: 11 } } : {}),
    };
    return `data: ${JSON.stringify(body)}\n\n`;
}

/** Scripted OpenAI-compatible chat completions stream: one read_file tool call, then an answer. */
class OpenAiScript {
    readonly bodies: string[] = [];
    private turn = 0;

    readonly fetch: typeof fetch = (_input, init) => {
        this.bodies.push(typeof init?.body === "string" ? init.body : "");
        const call = {
            index: 0,
            id: "call_1",
            type: "function",
            function: { name: "read_file", arguments: JSON.stringify({ path: "notes.txt" }) },
        };
        const events =
            this.turn++ === 0
                ? [chunk({ role: "assistant", tool_calls: [call] }, null), chunk({}, "tool_calls", true)]
                : [chunk({ role: "assistant", content: "끝" }, null), chunk({}, "stop", true)];
        const stream = events.join("") + "data: [DONE]\n\n";
        return Promise.resolve(new Response(stream, { headers: { "content-type": "text/event-stream" } }));
    };
}

class RecordingGate implements ModelRequestGate {
    readonly decisions: ModelRequestDecision[] = [];
    constructor(private readonly inner: ModelRequestGate) {}

    async check(request: OutboundModelRequest, signal: AbortSignal): Promise<ModelRequestDecision> {
        const decision = await this.inner.check(request, signal);
        this.decisions.push(decision);
        return decision;
    }
}

function gateFor(service: CountedService, requireExactCount: boolean): RecordingGate {
    const client = new HttpContextServiceClient({ baseUrl: service.url, internalToken: service.token, validator });
    return new RecordingGate(
        createModelRequestGate({
            counter: client.tokens,
            contextLimitTokens: 32768,
            safetyMarginTokens: 1024,
            requireExactCount,
        }),
    );
}

for (const mode of ["provider_estimate", "exact"] as const) {
    it(`sends the SDK's OpenAI-compatible requests through the gate (${mode} count)`, async () => {
        const script = new OpenAiScript();
        const holder: { gate?: RecordingGate } = {};
        const host = await startRuntimeHost([], {
            provider: PROVIDER,
            providerFetch: script.fetch,
            serviceEnv: {
                SECURECODE_TEST_REQUEST_FRAMING: "openai_chat",
                SECURECODE_MODEL_ID: MODEL,
                ...(mode === "exact" ? { SECURECODE_TEST_REQUEST_COUNT_MODE: "exact" } : {}),
            },
            gate: (service) => {
                holder.gate = gateFor(service, mode === "exact");
                return holder.gate;
            },
        });
        try {
            const sessionId = await createSession(host);
            const run = await createRun(host, sessionId, "notes.txt를 읽어 주세요");
            const done = await host.client.waitFor(run.run_id, isFinished);
            assert.equal(done.status, "completed", JSON.stringify(done.terminal));
            assert.equal(script.bodies.length, 2, "tool turn and answer turn reached the provider");
            const decisions = holder.gate?.decisions ?? [];
            assert.equal(decisions.length, 2);
            for (const decision of decisions) {
                assert.ok(decision.allow);
                assert.equal(decision.countMode, mode);
            }
            const first = JSON.parse(script.bodies[0] ?? "{}") as { model?: string; tools?: unknown[] };
            assert.equal(first.model, MODEL);
            assert.ok(Array.isArray(first.tools) && first.tools.length > 0, "OpenAI tool definitions are sent");
            assert.match(script.bodies[1] ?? "", /"tool_call_id":"call_1"/);
        } finally {
            await host.close();
        }
    });
}
