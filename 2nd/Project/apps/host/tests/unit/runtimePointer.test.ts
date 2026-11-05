/** Validate the legacy runtime pointer HTTP boundary, without touching a live provider or pointer database. */
import assert from "node:assert/strict";
import { it } from "node:test";
import { readRuntimePointer, storeRuntimePointer } from "../../src/pointer-hooks/runtimePointerHook.js";

const id = "11111111-aaaa-4444-bbbb-222222222222";
const scope = { workspaceId: "ws_12345678", sessionId: "ses_12345678", internalToken: "test".repeat(10) };
const pointer = `securecode://runtime/ws_12345678/ses_12345678/${id}?v=1`;

it("preserves small output and rejects invalid storage URLs or tokens without sending any request", async (t) => {
    const transport = t.mock.method(globalThis, "fetch", () => Promise.reject(new Error("unexpected network call")));
    assert.deepEqual(await storeRuntimePointer({ content: "small" }, scope), { stored: false });
    for (const options of [{ baseUrl: "https://external.example" }, { internalToken: "" }, { workspaceId: ".." }]) {
        await assert.rejects(storeRuntimePointer({ content: "x".repeat(4096) }, { ...scope, ...options }));
    }
    assert.equal(transport.mock.callCount(), 0);
});

it("fails closed if the pointer service returns a foreign pointer or a wrong byte count", async (t) => {
    let response: unknown = {
        pointer_id: id,
        pointer_uri: `securecode://runtime/other/ses_12345678/${id}`,
        byte_size: 4,
    };
    t.mock.method(globalThis, "fetch", () => Promise.resolve(Response.json(response)));
    const put = () => storeRuntimePointer({ content: "🔍" }, { ...scope, thresholdBytes: 4 });
    await assert.rejects(put(), /mismatch/);
    response = { pointer_id: id, pointer_uri: pointer, byte_size: 1 };
    await assert.rejects(put(), /mismatch/);
    response = { pointer_id: id, pointer_uri: pointer, byte_size: 4 };
    const stored = await put();
    assert.deepEqual(stored, { stored: true, pointerUri: pointer, pointerId: id, byteSize: 4 });
});

it("validates explicit reads against session, requested bounds and UTF-8 next cursor", async (t) => {
    let reply: unknown = { content: "한", byte_size: 7, truncated: true, next_cursor: 3 };
    const transport = t.mock.method(globalThis, "fetch", () => Promise.resolve(Response.json(reply)));
    await assert.rejects(readRuntimePointer(pointer.replace("/ses_12345678/", "/ses_98765432/"), scope));
    await assert.rejects(readRuntimePointer(pointer, scope, 0, 16385));
    await assert.rejects(readRuntimePointer(pointer.replace("?v=1", "?v=2"), scope));
    assert.equal(transport.mock.callCount(), 0);
    const legacy = await readRuntimePointer(
        `securecode://runtime/w1/s1/${id}`,
        { ...scope, workspaceId: "w1", sessionId: "s1" },
        0,
        4,
    );
    assert.equal(legacy.nextCursor, 3);
    assert.deepEqual(await readRuntimePointer(pointer, scope, 0, 4), {
        content: "한",
        byteSize: 7,
        truncated: true,
        nextCursor: 3,
    });
    reply = { content: "한", byte_size: 7, truncated: true, next_cursor: 1 };
    await assert.rejects(readRuntimePointer(pointer, scope, 0, 4), /boundaries/);
});
