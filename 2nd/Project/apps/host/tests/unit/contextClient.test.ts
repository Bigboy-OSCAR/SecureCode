/**
 * HttpContextServiceClient against a scripted loopback server: bearer token,
 * contract validation, error mapping, local Unicode rejection and NOT_IMPLEMENTED ports.
 */
import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { ContractValidator } from "@securecode/contracts";
import { ContextServiceError } from "../../src/context-client/contextServiceError.js";
import { HttpContextServiceClient } from "../../src/context-client/httpContextServiceClient.js";
import { loadSharedVectors } from "../support/sharedFixtures.js";

interface UnicodeVectors {
    cases: { name: string; text: string; expect: "valid" | "invalid_unicode"; utf8_bytes?: number }[];
}

const TOKEN = "i".repeat(40);
const vectors = loadSharedVectors<UnicodeVectors>("token-unicode-cases.json");
let nextResponse: { status: number; body: unknown; location?: string } = { status: 200, body: {} };
const received: { authorization: string | undefined; body: string }[] = [];

function scriptedHandler(request: IncomingMessage, response: ServerResponse): void {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
        received.push({ authorization: request.headers.authorization, body: Buffer.concat(chunks).toString("utf8") });
        response.writeHead(nextResponse.status, {
            "content-type": "application/json",
            ...(nextResponse.location ? { location: nextResponse.location } : {}),
        });
        response.end(JSON.stringify(nextResponse.body));
    });
}

function tokenResult(text: string): Record<string, unknown> {
    return {
        schema_version: "1",
        token_count: 3,
        count_mode: "provider_estimate",
        provider_id: "anthropic",
        model_id: "claude-sonnet-5-5",
        method: "anthropic_count_tokens",
        framing: "single_user_message",
        text_bytes: Buffer.byteLength(text, "utf8"),
        cached: false,
    };
}

describe("HttpContextServiceClient", () => {
    const server = createServer(scriptedHandler);
    const validator = ContractValidator.load();
    let client: HttpContextServiceClient;

    before(async () => {
        await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
        const port = (server.address() as AddressInfo).port;
        client = new HttpContextServiceClient({
            baseUrl: `http://127.0.0.1:${port}`,
            internalToken: TOKEN,
            validator,
            timeoutMs: 2000,
        });
    });

    after(() => {
        server.close();
    });

    for (const vector of vectors.cases.filter((item) => item.expect === "valid")) {
        it(`sends ${vector.name} unchanged with the bearer token`, async () => {
            nextResponse = { status: 200, body: tokenResult(vector.text) };
            const result = await client.tokens.count(vector.text);
            const sent = received.at(-1);
            assert.equal(sent?.authorization, `Bearer ${TOKEN}`);
            assert.equal((JSON.parse(sent?.body ?? "{}") as { text: string }).text, vector.text);
            assert.equal(result.text_bytes, vector.utf8_bytes);
            assert.equal(result.count_mode, "provider_estimate");
        });
    }

    for (const vector of vectors.cases.filter((item) => item.expect === "invalid_unicode")) {
        it(`rejects ${vector.name} before any request`, async () => {
            const sentBefore = received.length;
            await assert.rejects(
                client.tokens.count(vector.text),
                (error: unknown) => error instanceof ContextServiceError && error.code === "VALIDATION_FAILED",
            );
            assert.equal(received.length, sentBefore);
        });
    }

    it("rejects empty or oversized input before sending it", async () => {
        const count = received.length;
        await assert.rejects(
            client.tokens.count(""),
            (error: unknown) => error instanceof ContextServiceError && error.code === "VALIDATION_FAILED",
        );
        await assert.rejects(
            client.tokens.count("🔍".repeat(262145)),
            (error: unknown) => error instanceof ContextServiceError && error.code === "PAYLOAD_TOO_LARGE",
        );
        assert.equal(received.length, count);
    });

    it("does not forward token payloads across a 307 or accept unbounded response text", async () => {
        const count = received.length;
        nextResponse = { status: 307, location: "/unexpected", body: {} };
        await assert.rejects(
            client.tokens.count("private test input"),
            (error: unknown) => error instanceof ContextServiceError && error.code === "SERVICE_UNAVAILABLE",
        );
        assert.equal(received.length, count + 1);
        nextResponse = { status: 200, body: "x".repeat(300000) };
        await assert.rejects(
            client.health(),
            (error: unknown) => error instanceof ContextServiceError && error.code === "SERVICE_UNAVAILABLE",
        );
    });

    it("maps a contract error response to ContextServiceError", async () => {
        nextResponse = {
            status: 503,
            body: {
                schema_version: "1",
                error: {
                    code: "TOKENIZER_UNAVAILABLE",
                    message: "토큰 계수기를 사용할 수 없습니다.",
                    retryable: false,
                    request_id: "req_0123456789ab",
                    details: { reason: "api_key_missing" },
                },
            },
        };
        await assert.rejects(
            client.tokens.count("x"),
            (error: unknown) =>
                error instanceof ContextServiceError && error.code === "TOKENIZER_UNAVAILABLE" && !error.retryable,
        );
    });

    it("rejects a response that breaks the contract", async () => {
        nextResponse = { status: 200, body: { ...tokenResult("x"), count_mode: "chars_div_4" } };
        await assert.rejects(client.tokens.count("x"), /does not match/);
        nextResponse = { status: 200, body: tokenResult("different text") };
        await assert.rejects(client.tokens.count("x"), /input size mismatch/);
    });

    it("reports SERVICE_UNAVAILABLE when nothing listens", async () => {
        const offline = new HttpContextServiceClient({
            baseUrl: "http://127.0.0.1:9",
            internalToken: TOKEN,
            validator,
            timeoutMs: 1000,
        });
        await assert.rejects(
            offline.health(),
            (error: unknown) =>
                error instanceof ContextServiceError && error.code === "SERVICE_UNAVAILABLE" && error.retryable,
        );
    });
});
