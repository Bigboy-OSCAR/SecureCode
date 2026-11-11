import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { parseModelListResponse } from "@securecode/contracts";
import { ModelManager } from "../../src/app/models/modelManager.js";
import type { ModelProfile } from "../../src/app/models/modelProfiles.js";
import { BrowserAuth, SESSION_TTL_MS } from "../../src/security/browserAuth.js";

const profile: ModelProfile = {
    model_id: "local-test",
    display_name: "Local model",
    runtime: "llama-cpp",
    context_limit_tokens: 32768,
    available: true,
    baseUrl: "http://127.0.0.1:8080/v1",
    modelPath: "/private/model.gguf",
    executable: "/private/llama-server",
    apiKey: "fixture-private-key",
};

test("model switching blocks concurrent turns, exposes loading, persists only the model ID and fails closed", async () => {
    const directory = mkdtempSync(join(tmpdir(), "localdesk-models-"));
    let running = true;
    let finish: (() => void) | undefined;
    let fail = false;
    const manager = new ModelManager({
        profiles: [profile],
        selectionFile: join(directory, "selection.json"),
        activeModelId: null,
        hasActiveRuns: () => running,
        activate: async () => {
            if (fail) throw new Error("private provider details");
            await new Promise<void>((resolve) => {
                finish = resolve;
            });
        },
    });
    try {
        await assert.rejects(manager.select(profile.model_id), /끝난 뒤/);
        running = false;
        const loading = manager.select(profile.model_id);
        assert.equal(manager.snapshot().status, "loading");
        assert.equal(manager.ready(), false);
        await assert.rejects(manager.select(profile.model_id), /끝난 뒤/);
        finish?.();
        const result = parseModelListResponse(await loading);
        assert.equal(result.active_model_id, profile.model_id);
        assert.equal(manager.savedSelection(), profile.model_id);
        assert.equal(JSON.stringify(result).includes("private"), false);
        const failed = new ModelManager({
            profiles: [profile],
            selectionFile: join(directory, "failed.json"),
            activeModelId: null,
            hasActiveRuns: () => false,
            activate: async () => {
                throw new Error("secret");
            },
        });
        fail = true;
        await assert.rejects(failed.select(profile.model_id));
        assert.equal(failed.ready(), false);
        assert.equal(failed.snapshot().active_model_id, null);
        assert.equal(failed.snapshot().status, "error");
        assert.equal(JSON.stringify(failed.snapshot()).includes("secret"), false);
    } finally {
        rmSync(directory, { recursive: true, force: true });
    }
});

test("launcher can reissue a one-time code after browser expiry without replacing host state", () => {
    let now = 1000;
    const auth = new BrowserAuth("old-fixture-bootstrap", () => now);
    const first = auth.exchange("old-fixture-bootstrap");
    assert.equal(first.kind, "ok");
    if (first.kind !== "ok") return;
    now += SESSION_TTL_MS + 1;
    assert.equal(auth.isAuthenticated(`securecode_session=${first.token}`), false);
    const code = auth.reissueCode();
    assert.equal(auth.exchange("old-fixture-bootstrap").kind, "invalid");
    const renewed = auth.exchange(code);
    assert.equal(renewed.kind, "ok");
    assert.equal(auth.exchange(code).kind, "invalid");
});
