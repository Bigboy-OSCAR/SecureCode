import assert from "node:assert/strict";
import { test } from "node:test";
import { ModelServers } from "../../src/app/models/modelServers.js";
import type { ModelProfile } from "../../src/app/models/modelProfiles.js";
import type { OwnedStudioModel } from "../../src/app/models/studioRuntime.js";
import { startTestHost } from "../support/hostHarness.js";
import { FakeRuntime } from "../support/fakeRuntime.js";

const profile: ModelProfile = {
    model_id: "fixture-model",
    display_name: "Fixture",
    runtime: "lm-studio",
    context_limit_tokens: 32768,
    available: true,
    baseUrl: "http://127.0.0.1:1234/v1",
    modelPath: "fixture-model",
    executable: "/fixture/lms",
    apiKey: "fixture-key",
};

function entered() {
    let signal: (() => void) | undefined;
    const promise = new Promise<void>((resolve) => {
        signal = resolve;
    });
    return { promise, signal: () => signal?.() };
}

test("closing during a cold load aborts the official load signal and waits for cancellation", async () => {
    const started = entered();
    let cancelled = false;
    const servers = new ModelServers({
        load: async (_profile, signal) => {
            started.signal();
            return new Promise<OwnedStudioModel | null>((_resolve, reject) => {
                signal.addEventListener(
                    "abort",
                    () => {
                        cancelled = true;
                        reject(signal.reason instanceof Error ? signal.reason : new Error("cancelled"));
                    },
                    { once: true },
                );
            });
        },
    });
    const loading = servers.load(profile);
    const rejected = assert.rejects(loading, /model load stopped/);
    await started.promise;
    await servers.stop();
    await rejected;
    assert.equal(cancelled, true);
    await servers.stop();
});

test("a load finishing concurrently with close releases that owned handle exactly once", async () => {
    const started = entered();
    let stopped = 0;
    const servers = new ModelServers({
        load: async (_profile, signal) => {
            started.signal();
            return new Promise<OwnedStudioModel>((resolve) => {
                signal.addEventListener(
                    "abort",
                    () =>
                        resolve({
                            stop: async () => {
                                stopped += 1;
                            },
                        }),
                    { once: true },
                );
            });
        },
    });
    const loading = servers.load(profile);
    const rejected = assert.rejects(loading, /model load stopped/);
    await started.promise;
    await servers.stop();
    await rejected;
    await servers.stop();
    assert.equal(stopped, 1);
});

test("closing before load starts does not start a server and an existing external model is never owned", async () => {
    let calls = 0;
    const servers = new ModelServers({
        load: async () => {
            calls += 1;
            return null;
        },
    });
    const loading = servers.load(profile);
    const rejected = assert.rejects(loading, /model load stopped/);
    await servers.stop();
    await rejected;
    assert.equal(calls, 0);
    await servers.load(profile);
    await servers.stop();
    assert.equal(calls, 1);
});

test("host shutdown cancels model selection before waiting for its pending HTTP response", async () => {
    const started = entered();
    let rejectLoad: ((error: Error) => void) | undefined;
    let stopped = false;
    const servers = {
        async load() {
            started.signal();
            await new Promise<void>((_resolve, reject) => {
                rejectLoad = reject;
            });
        },
        async stop() {
            stopped = true;
            rejectLoad?.(new Error("stopped"));
        },
    };
    const host = await startTestHost({
        runtimeFactory: async () => new FakeRuntime(),
        transformer: null,
        gate: null,
        modelProfiles: [profile],
        modelServers: servers,
    });
    let timer: NodeJS.Timeout | undefined;
    try {
        await host.client.bootstrap();
        const selection = host.client.send(
            "POST",
            "/api/v1/models/select",
            { model_id: profile.model_id },
            { connection: "close" },
        );
        await started.promise;
        await Promise.race([
            host.close(),
            new Promise<void>((_resolve, reject) => {
                timer = setTimeout(() => reject(new Error("shutdown waited for uncancelled model request")), 2000);
            }),
        ]);
        assert.equal(stopped, true);
        assert.equal((await selection).status, 502);
    } finally {
        clearTimeout(timer);
        await servers.stop();
        host.host.server.closeAllConnections();
        await host.close();
    }
});
