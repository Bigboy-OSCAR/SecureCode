/**
 * Live check of the local llama.cpp token counter (opt-in, `npm run test:live`). The context-service
 * counts a chat request through the server's /apply-template + /tokenize; the same request is then sent
 * to the server's /v1/chat/completions with max_tokens 1, and the reported usage.prompt_tokens must be
 * equal. Only a PASS here supports the counter's "exact" label for the configured model.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ContractValidator, SCHEMA_REFS, type TokenCountResult } from "@securecode/contracts";
import type { StepResult } from "./report.js";
import { findFreePorts, startServices } from "./services.js";

type ChatRequest = Record<string, unknown>;

function cases(model: string): { name: string; request: ChatRequest }[] {
    const tools = [
        {
            type: "function",
            function: {
                name: "read_file",
                description: "Read a workspace file",
                parameters: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
            },
        },
    ];
    return [
        {
            name: "korean chat",
            request: {
                model,
                messages: [
                    { role: "system", content: "You are SecureCode." },
                    { role: "user", content: "한글로 짧게 답하세요: 포인터란? 🌏" },
                ],
            },
        },
        {
            name: "tools and a tool result",
            request: {
                model,
                tools,
                messages: [
                    { role: "system", content: "Use tools when needed." },
                    { role: "user", content: "notes.txt를 읽어 주세요" },
                    {
                        role: "assistant",
                        content: null,
                        tool_calls: [
                            {
                                id: "call_1",
                                type: "function",
                                function: { name: "read_file", arguments: '{"path":"notes.txt"}' },
                            },
                        ],
                    },
                    { role: "tool", tool_call_id: "call_1", content: "hello\n세계" },
                ],
            },
        },
    ];
}

export async function liveLlamaCppSteps(): Promise<StepResult[]> {
    if (process.env.SECURECODE_TOKEN_COUNTER !== "llama-cpp") return [];
    const name = "live llama.cpp exact count";
    if (process.env.SECURECODE_LIVE_SMOKE !== "1") {
        return [{ name, status: "SKIPPED", detail: "SECURECODE_LIVE_SMOKE is not 1 (opt-in)" }];
    }
    const baseUrl = process.env.SECURECODE_PROVIDER_BASE_URL?.replace(/\/+$/, "");
    const model = process.env.SECURECODE_MODEL_ID;
    if (!baseUrl || !model) {
        return [
            { name, status: "SKIPPED", detail: "SECURECODE_PROVIDER_BASE_URL and SECURECODE_MODEL_ID are required" },
        ];
    }
    const apiKey = process.env.SECURECODE_PROVIDER_API_KEY?.trim();
    const auth: Record<string, string> = apiKey ? { authorization: `Bearer ${apiKey}` } : {};
    const validator = ContractValidator.load();
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-live-llama-"));
    const services = await startServices({ ...(await findFreePorts()), dataDir });
    const results: StepResult[] = [];
    try {
        for (const item of cases(model)) {
            const counted = await fetch(`${services.serviceUrl}/internal/v1/tokens/request`, {
                method: "POST",
                headers: { authorization: `Bearer ${services.internalToken}`, "content-type": "application/json" },
                body: JSON.stringify({
                    schema_version: "1",
                    provider_id: "openai-compatible",
                    model_id: model,
                    request: item.request,
                }),
            });
            const countBody: unknown = await counted.json();
            if (!counted.ok || !validator.validate(SCHEMA_REFS.tokenCountResult, countBody).valid) {
                results.push({ name: `${name}: ${item.name}`, status: "FAIL", detail: JSON.stringify(countBody) });
                continue;
            }
            const count = countBody as TokenCountResult;
            const real = await fetch(`${baseUrl}/chat/completions`, {
                method: "POST",
                headers: { ...auth, "content-type": "application/json" },
                body: JSON.stringify({ ...item.request, max_tokens: 1, stream: false, temperature: 0 }),
            });
            const usage = ((await real.json()) as { usage?: { prompt_tokens?: number } }).usage;
            const passed = count.count_mode === "exact" && usage?.prompt_tokens === count.token_count;
            results.push({
                name: `${name}: ${item.name}`,
                status: passed ? "PASS" : "FAIL",
                detail: `counted ${count.token_count} (${count.count_mode}), server prompt_tokens ${usage?.prompt_tokens ?? "none"}`,
            });
        }
    } finally {
        await services.stopAll();
        rmSync(dataDir, { recursive: true, force: true });
    }
    return results;
}
