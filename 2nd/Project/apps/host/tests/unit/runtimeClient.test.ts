/** 4.4 Runtime client: request shapes, streaming upload, contract checks, scope/byte mismatches and error envelopes. */
import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, it } from "node:test";
import { ContractValidator } from "@securecode/contracts";
import { ContextServiceError } from "../../src/context-client/contextServiceError.js";
import { createRuntimeClient } from "../../src/pointer-hooks/runtimeClient.js";

const SCOPE = { workspaceId: "ws_12345678", sessionId: "ses_12345678" };
const TOKEN = "t".repeat(40);
const POINTER = `securecode://runtime/ws_12345678/ses_12345678/11111111-2222-4333-8444-555555555555?v=1`;
const META = { origin: "run_command", mediaType: "text/plain", truncatedBeforeStorage: false };

interface Seen {
    path: string;
    headers: IncomingMessage["headers"];
    body: Buffer;
    aborted: boolean;
}

const seen: Seen[] = [];
let reply: (seen: Seen, response: ServerResponse) => void = () => undefined;
let baseUrl = "";
const server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    const record: Seen = { path: request.url ?? "", headers: request.headers, body: Buffer.alloc(0), aborted: false };
    seen.push(record);
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("aborted", () => (record.aborted = true));
    request.on("end", () => {
        record.body = Buffer.concat(chunks);
        reply(record, response);
    });
});

function descriptor(byteSize: number, pointer = POINTER): Record<string, unknown> {
    return {
        schema_version: "1",
        pointer,
        kind: "runtime",
        workspace_id: SCOPE.workspaceId,
        session_id: SCOPE.sessionId,
        revision: 1,
        media_type: "text/plain",
        byte_size: byteSize,
        preview: "p",
        available_operations: ["read", "search"],
        provenance: { created_at: "2026-11-10T00:00:00Z", origin: "run_command" },
        expires_at: "2026-11-11T00:00:00Z",
    };
}

function json(response: ServerResponse, status: number, body: unknown): void {
    response.writeHead(status, { "content-type": "application/json" });
    response.end(JSON.stringify(body));
}

const client = () => createRuntimeClient({ baseUrl, internalToken: TOKEN, validator: ContractValidator.load() });
const signal = (): AbortSignal => new AbortController().signal;

before(async () => {
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

after(async () => {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
});

it("stores with origin metadata and validates the returned descriptor", async () => {
    reply = (record, response) => {
        const size = (JSON.parse(record.body.toString()) as { content: string }).content.length;
        json(response, 200, { pointer_id: "x", pointer_uri: POINTER, byte_size: size, descriptor: descriptor(size) });
    };
    const stored = await client().store(SCOPE, "hello", { ...META, truncatedBeforeStorage: true }, signal());
    assert.deepEqual(stored, { pointer: POINTER, byteSize: 5 });
    const request = seen.at(-1);
    assert.equal(request?.path, "/internal/v1/runtime/pointers");
    assert.equal(request?.headers.authorization, `Bearer ${TOKEN}`);
    assert.deepEqual(JSON.parse(request?.body.toString() ?? ""), {
        workspace_id: SCOPE.workspaceId,
        session_id: SCOPE.sessionId,
        content: "hello",
        media_type: "text/plain",
        origin: "run_command",
        truncated_before_storage: true,
    });
});

it("rejects foreign scopes, byte mismatches and maps error envelopes", async () => {
    const foreign = POINTER.replace("ses_12345678", "ses_87654321");
    reply = (_record, response) =>
        json(response, 200, {
            pointer_uri: foreign,
            byte_size: 5,
            descriptor: { ...descriptor(5, foreign), session_id: "ses_87654321" },
        });
    await assert.rejects(client().store(SCOPE, "hello", META, signal()), /invalid response/);
    reply = (_record, response) =>
        json(response, 200, { pointer_uri: POINTER, byte_size: 4, descriptor: descriptor(4) });
    await assert.rejects(client().store(SCOPE, "hello", META, signal()), /invalid response/);
    reply = (_record, response) =>
        json(response, 507, {
            schema_version: "1",
            error: {
                code: "QUOTA_EXCEEDED",
                message: "세션 용량 한도를 초과했습니다",
                retryable: false,
                request_id: "req_123456789012",
                details: { reason: "session_limit" },
            },
        });
    await assert.rejects(client().store(SCOPE, "hello", META, signal()), (error: unknown) => {
        assert.ok(error instanceof ContextServiceError);
        assert.equal(error.code, "QUOTA_EXCEEDED");
        return true;
    });
    const calls = seen.length;
    await assert.rejects(client().store({ workspaceId: "..", sessionId: "x" }, "hello", META, signal()));
    await assert.rejects(
        createRuntimeClient({
            baseUrl: "http://example.com",
            internalToken: TOKEN,
            validator: ContractValidator.load(),
        }).store(SCOPE, "hello", META, signal()),
    );
    assert.equal(seen.length, calls, "invalid scope or non-loopback URL sends nothing");
});

it("streams chunks with scope headers and aborts without a stored object", async () => {
    reply = (record, response) =>
        json(response, 200, {
            pointer_uri: POINTER,
            byte_size: record.body.length,
            descriptor: descriptor(record.body.length),
        });
    const upload = client().openUpload(SCOPE, META, signal());
    for (let index = 0; index < 50; index += 1) await upload.write(Buffer.from("가나다".repeat(1000)));
    const stored = await upload.finish();
    const request = seen.at(-1);
    assert.equal(stored.byteSize, 9000 * 50);
    assert.equal(request?.path, "/internal/v1/runtime/stream");
    assert.equal(request?.headers["content-type"], "application/octet-stream");
    assert.equal(request?.headers["x-securecode-session-id"], SCOPE.sessionId);
    assert.equal(request?.headers["x-securecode-origin"], "run_command");
    assert.equal(request?.body.toString(), "가나다".repeat(50_000));
    reply = () => undefined;
    const aborted = client().openUpload(SCOPE, META, signal());
    await aborted.write(Buffer.from("partial"));
    aborted.abort();
    await assert.rejects(aborted.finish(), /stream upload failed/);
});

it("validates read and search results against the contract and the requested pointer", async () => {
    reply = (record, response) => {
        const body = JSON.parse(record.body.toString()) as { pointer: string };
        if (record.path.endsWith("/read")) {
            json(response, 200, {
                schema_version: "1",
                pointer: body.pointer,
                content: "line 2",
                provenance: { media_type: "text/plain", byte_size: 100, revision: 1 },
                truncated: false,
                token_count: 6,
                count_mode: "provider_estimate",
            });
        } else {
            json(response, 200, {
                schema_version: "1",
                pointer: POINTER,
                matches: [],
                truncated: false,
                token_count: 0,
                count_mode: "exact",
            });
        }
    };
    const read = await client().read(SCOPE, { pointer: POINTER, selector: { type: "line", start: 2 } }, signal());
    assert.equal(read.content, "line 2");
    assert.equal((JSON.parse(seen.at(-1)?.body.toString() ?? "") as { schema_version: string }).schema_version, "1");
    const other = POINTER.replace("11111111", "22222222");
    await assert.rejects(client().search(SCOPE, { pointer: other, query: "x" }, signal()), /invalid response/);
    reply = (_record, response) => json(response, 200, { content: "raw" });
    await assert.rejects(client().read(SCOPE, { pointer: POINTER }, signal()));
});
