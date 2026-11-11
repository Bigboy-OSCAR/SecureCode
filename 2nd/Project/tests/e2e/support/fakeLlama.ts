/**
 * Fixture provider for the browser E2E suite: a loopback stand-in for a llama.cpp server. It answers the
 * OpenAI-compatible streaming chat endpoint from a script and the two token-counting endpoints the
 * context-service uses (`/tokenize`, `/apply-template`), so the real host, SDK, request gate and service
 * run unchanged. Every chat request body is kept so a test can check what reached the "model".
 * This is a fixture, not a model: live runs use `npm run test:live` against a real provider.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export const FAKE_MODEL_ID = "e2e-fixture-model";

export interface TurnContext {
    /** The newest tool-result message the SDK sent back, as text. */
    lastToolResult: string;
}

export type FakeTurn =
    | { text: string }
    | { tool: string; args: Record<string, unknown> | ((context: TurnContext) => Record<string, unknown>) }
    /** Streams nothing and keeps the request open until the host aborts it (cancel tests). */
    | { hold: true }
    /** Fails the request with this HTTP status, like a provider outage. */
    | { status: number };

export interface FakeLlama {
    baseUrl: string;
    readonly requests: string[];
    script(turns: FakeTurn[]): void;
    close(): Promise<void>;
}

function readBody(request: IncomingMessage): Promise<string> {
    return new Promise((resolve, reject) => {
        const chunks: Buffer[] = [];
        request.on("data", (chunk: Buffer) => chunks.push(chunk));
        request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
        request.on("error", reject);
    });
}

function json(response: ServerResponse, body: unknown): void {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(body));
}

function lastToolResult(body: { messages?: { role?: string; content?: unknown }[] }): string {
    const tool = [...(body.messages ?? [])].reverse().find((message) => message.role === "tool");
    return typeof tool?.content === "string" ? tool.content : JSON.stringify(tool?.content ?? "");
}

function chunk(delta: Record<string, unknown>, finish: string | null): string {
    const body = {
        id: "chatcmpl-e2e",
        object: "chat.completion.chunk",
        created: 0,
        model: FAKE_MODEL_ID,
        choices: [{ index: 0, delta, finish_reason: finish }],
        ...(finish ? { usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } } : {}),
    };
    return `data: ${JSON.stringify(body)}\n\n`;
}

function stream(
    response: ServerResponse,
    turn: Extract<FakeTurn, { text: string } | { tool: string }>,
    context: TurnContext,
): void {
    response.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    if ("text" in turn) {
        response.write(chunk({ role: "assistant", content: turn.text }, null));
        response.write(chunk({}, "stop"));
    } else {
        const args = typeof turn.args === "function" ? turn.args(context) : turn.args;
        const call = {
            index: 0,
            id: `call_${Math.random().toString(36).slice(2, 10)}`,
            type: "function",
            function: { name: turn.tool, arguments: JSON.stringify(args) },
        };
        response.write(chunk({ role: "assistant", tool_calls: [call] }, null));
        response.write(chunk({}, "tool_calls"));
    }
    response.end("data: [DONE]\n\n");
}

export async function startFakeLlama(): Promise<FakeLlama> {
    const requests: string[] = [];
    let turns: FakeTurn[] = [];
    const server: Server = createServer((request, response) => {
        void (async () => {
            const text = request.method === "POST" ? await readBody(request) : "";
            const path = (request.url ?? "/").split("?")[0];
            if (path === "/health") return json(response, { status: "ok" });
            if (path === "/tokenize") {
                const raw = (JSON.parse(text) as { content?: unknown }).content;
                const content = typeof raw === "string" ? raw : "";
                // Deterministic stand-in for a tokenizer: one token per 4 UTF-8 bytes.
                return json(response, { tokens: new Array(Math.ceil(Buffer.byteLength(content) / 4)).fill(0) });
            }
            if (path === "/apply-template") {
                const body = JSON.parse(text) as { messages?: unknown; tools?: unknown };
                return json(response, { prompt: JSON.stringify({ messages: body.messages, tools: body.tools }) });
            }
            if (path === "/v1/chat/completions") {
                requests.push(text);
                const body = JSON.parse(text) as { messages?: { role?: string; content?: unknown }[] };
                const turn = turns.shift() ?? { text: "(fixture: no scripted turn left)" };
                if ("status" in turn) {
                    response.writeHead(turn.status, { "content-type": "application/json" });
                    response.end(JSON.stringify({ error: { message: "FIXTURE-PROVIDER-SECRET-DETAIL" } }));
                    return undefined;
                }
                if ("hold" in turn) {
                    response.writeHead(200, { "content-type": "text/event-stream" });
                    request.on("close", () => response.end());
                    return undefined;
                }
                return stream(response, turn, { lastToolResult: lastToolResult(body) });
            }
            response.writeHead(404).end();
            return undefined;
        })().catch(() => {
            if (!response.headersSent) response.writeHead(500);
            response.end();
        });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    return {
        baseUrl: `http://127.0.0.1:${port}/v1`,
        requests,
        script(next) {
            turns = [...next];
        },
        close: () =>
            new Promise((resolve) => {
                server.closeAllConnections();
                server.close(() => resolve());
            }),
    };
}

/** Pulls the Runtime Pointer URI out of a stored-output descriptor the SDK returned as a tool result. */
export function runtimePointerIn(toolResult: string): string {
    const match = /securecode:\/\/runtime\/[A-Za-z0-9_./?=-]+/.exec(toolResult.replaceAll("\\/", "/"));
    if (!match) throw new Error("the tool result carries no runtime pointer");
    return match[0];
}
