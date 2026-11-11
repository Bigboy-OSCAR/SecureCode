import assert from "node:assert/strict";
import { test } from "node:test";
import type { AppEvent } from "@securecode/contracts";
import { ApiClientError } from "../src/api/apiErrors.js";
import { ApiHttpClient } from "../src/api/httpClient.js";
import { SseClient } from "../src/api/events/sseClient.js";
import { parseApiPayload, serializeApiRequest } from "../src/api/mappers/contractMapper.js";
import bootstrapFixture from "../../../contracts/fixtures/api/bootstrap-response.valid.json";
import terminalEventFixture from "../../../contracts/fixtures/events/run-status-cancelled-terminal.valid.json";
import replayUnavailableFixture from "../../../contracts/fixtures/events/stream-replay-unavailable.valid.json";
import outputEventFixture from "../../../contracts/fixtures/events/run-output-delta-korean.valid.json";

test("HTTP boundary validates bootstrap response and keeps one-time code in the request body", async () => {
    let requestUrl = "";
    let requestInit: RequestInit | undefined;
    const fetcher: typeof fetch = async (input, init) => {
        requestUrl = input instanceof Request ? input.url : input instanceof URL ? input.href : input;
        requestInit = init;
        return new Response(JSON.stringify(bootstrapFixture.data), {
            status: 200,
            headers: { "content-type": "application/json" },
        });
    };
    const client = new ApiHttpClient("/api/v1", fetcher);

    await client.bootstrap({ code: "one-time-code-1234" });

    assert.equal(requestUrl, "/api/v1/auth/bootstrap");
    assert.equal(requestInit?.credentials, "same-origin");
    assert.equal(requestInit?.headers instanceof Headers ? requestInit.headers.get("last-event-id") : null, null);
    const requestBody = requestInit?.body;
    assert.deepEqual(JSON.parse(typeof requestBody === "string" ? requestBody : ""), { code: "one-time-code-1234" });
});

test("HTTP boundary calls browser fetch with the global receiver", async () => {
    const fetcher: typeof fetch = function (this: unknown) {
        assert.equal(this, globalThis);
        return Promise.resolve(
            new Response(JSON.stringify(bootstrapFixture.data), {
                status: 200,
                headers: { "content-type": "application/json" },
            }),
        );
    };

    await new ApiHttpClient("/api/v1", fetcher).bootstrap({ code: "one-time-code-1234" });
});

test("HTTP boundary rejects malformed success and error payloads without exposing response text", async () => {
    const secret = "provider-secret-should-not-be-displayed";
    const malformedSuccess: typeof fetch = async () =>
        new Response(JSON.stringify({ schema_version: "1", run_id: "run_invalid", secret }), {
            status: 200,
            headers: { "content-type": "application/json" },
        });
    const client = new ApiHttpClient("/api/v1", malformedSuccess);

    await assert.rejects(client.getRun("run_test"), (error: unknown) => {
        assert.ok(error instanceof ApiClientError);
        assert.equal(error.kind, "contract");
        assert.equal(error.message.includes(secret), false);
        return true;
    });

    const malformedError: typeof fetch = async () =>
        new Response(JSON.stringify({ error: { message: secret } }), {
            status: 500,
            headers: { "content-type": "application/json" },
        });
    await assert.rejects(new ApiHttpClient("/api/v1", malformedError).getHealth(), (error: unknown) => {
        assert.ok(error instanceof ApiClientError);
        assert.equal(error.kind, "contract");
        assert.equal(error.message.includes(secret), false);
        return true;
    });
});

test("HTTP boundary distinguishes network, timeout, authentication, authorization, and server failures", async () => {
    const unauthenticated = errorPayload("UNAUTHENTICATED");
    const forbidden = errorPayload("FORBIDDEN");
    const serverFailure = errorPayload("INTERNAL_ERROR");
    const responses = new Map([
        [401, unauthenticated],
        [403, forbidden],
        [503, serverFailure],
    ]);

    for (const [status, payload] of responses) {
        const client = new ApiHttpClient(
            "/api/v1",
            async () =>
                new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }),
        );
        await assert.rejects(client.getHealth(), (error: unknown) => {
            assert.ok(error instanceof ApiClientError);
            assert.equal(error.kind, status === 401 ? "unauthorized" : status === 403 ? "forbidden" : "server");
            assert.equal(error.message.includes("provider-secret"), false);
            return true;
        });
    }

    await assert.rejects(
        new ApiHttpClient("/api/v1", async () => {
            throw new TypeError("fetch failed");
        }).getHealth(),
        (error: unknown) => error instanceof ApiClientError && error.kind === "network",
    );
    await assert.rejects(
        new ApiHttpClient("/api/v1", async () => {
            throw new DOMException("timed out", "TimeoutError");
        }).getHealth(),
        (error: unknown) => error instanceof ApiClientError && error.kind === "timeout",
    );
});

test("SSE boundary validates events, sequence IDs, same-origin credentials, and replay notices", async () => {
    const terminalEvent = terminalEventFixture.data as AppEvent;
    const capturedHeaders: string[] = [];
    const terminalClient = new SseClient(
        "/api/v1",
        async (_input, init) => {
            capturedHeaders.push(new Headers(init?.headers).get("last-event-id") ?? "");
            return sseResponse(terminalEvent, String(terminalEvent.sequence));
        },
        0,
    );
    const observedTerminal = waitForEvent(terminalClient, terminalEvent, 8);
    await observedTerminal.promise;
    observedTerminal.stop();
    assert.deepEqual(capturedHeaders, ["8"]);

    const replayEvent = replayUnavailableFixture.data as AppEvent;
    const observedReplay = waitForEvent(
        new SseClient("/api/v1", async () => sseResponse(replayEvent, null), 0),
        replayEvent,
        2,
    );
    await observedReplay.promise;
    observedReplay.stop();
});

test("SSE boundary calls browser fetch with the global receiver", async () => {
    const terminalEvent = terminalEventFixture.data as AppEvent;
    const fetcher: typeof fetch = function (this: unknown) {
        assert.equal(this, globalThis);
        return Promise.resolve(sseResponse(terminalEvent, String(terminalEvent.sequence)));
    };
    const observed = waitForEvent(new SseClient("/api/v1", fetcher, 0), terminalEvent, 0);
    await observed.promise;
    observed.stop();
});

test("SSE boundary rejects mismatched event IDs as invalid host payload", async () => {
    const event = terminalEventFixture.data as AppEvent;
    const invalid = { ...event, sequence: event.sequence + 1 };
    let disconnect: Error | undefined;
    const stream = new SseClient("/api/v1", async () => sseResponse(invalid, String(event.sequence)), 0);
    const stopped = new Promise<void>((resolve) => {
        stream.subscribe(
            event.run_id,
            event.sequence - 1,
            () => assert.fail("Invalid event must not be delivered."),
            (error) => {
                disconnect = error;
                resolve();
            },
        );
    });
    await stopped;
    assert.ok(disconnect instanceof ApiClientError);
    assert.equal(disconnect.kind, "contract");
});

test("SSE reconnect sends the last parsed sequence and recovers after a transient close", async () => {
    const outputEvent = outputEventFixture.data as AppEvent;
    const terminalEvent = {
        ...terminalEventFixture.data,
        event_id: "evt_01J9Z6Q4EV0999",
        sequence: outputEvent.sequence + 1,
    } as AppEvent;
    const cursors: string[] = [];
    let responseCount = 0;
    const client = new SseClient(
        "/api/v1",
        async (_input, init) => {
            cursors.push(new Headers(init?.headers).get("last-event-id") ?? "");
            responseCount += 1;
            return responseCount === 1
                ? sseResponse(outputEvent, String(outputEvent.sequence))
                : sseResponse(terminalEvent, String(terminalEvent.sequence));
        },
        1,
    );
    const received = new Promise<AppEvent>((resolve, reject) => {
        client.subscribe(
            outputEvent.run_id,
            outputEvent.sequence - 1,
            (event) => {
                if (event.type === "run.status_changed" && event.payload.terminal) {
                    resolve(event);
                }
            },
            (error) => {
                if (error?.kind !== "network") {
                    reject(error ?? new Error("SSE disconnected"));
                }
            },
        );
    });

    await received;
    assert.deepEqual(cursors, [String(outputEvent.sequence - 1), String(outputEvent.sequence)]);
});

function errorPayload(code: string): unknown {
    return {
        schema_version: "1",
        error: {
            code,
            message: "provider-secret must not be rendered",
            retryable: false,
            request_id: "req_01J9Z6Q4TEST",
        },
    };
}

function sseResponse(event: AppEvent, id: string | null): Response {
    const text = `${id === null ? "" : `id: ${id}\n`}event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
    return new Response(text, {
        status: 200,
        headers: { "content-type": "text/event-stream; charset=utf-8" },
    });
}

function waitForEvent(
    client: SseClient,
    expected: AppEvent,
    sequence: number,
): { promise: Promise<AppEvent>; stop: () => void } {
    let stop = (): void => undefined;
    const promise = new Promise<AppEvent>((resolve, reject) => {
        stop = client.subscribe(
            expected.run_id,
            sequence,
            (event) => resolve(event),
            (error) => reject(error ?? new Error("SSE disconnected")),
        );
    });
    return { promise, stop };
}

test("mapper validates against the shared JSON schema", () => {
    assert.deepEqual(parseApiPayload("bootstrapResponse", bootstrapFixture.data), bootstrapFixture.data);
    assert.deepEqual(parseApiPayload("appEvent", terminalEventFixture.data), terminalEventFixture.data);
    assert.throws(() => parseApiPayload("runSnapshot", { schema_version: "1" }));
    assert.deepEqual(
        serializeApiRequest("workspaceCreateRequest", {
            displayName: "Project",
            rootPath: "/tmp/project",
            idempotencyKey: "ui-test-key-1234",
        }),
        {
            display_name: "Project",
            root_path: "/tmp/project",
            idempotency_key: "ui-test-key-1234",
        },
    );
});
