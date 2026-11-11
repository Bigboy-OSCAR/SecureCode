/** Owns only model processes started by this host; never stops unrelated local servers. */
import { spawn, type ChildProcess } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import type { ModelProfile } from "./modelProfiles.js";

import { LocalStudioRuntime, type OwnedStudioModel, type StudioRuntime } from "./studioRuntime.js";

export class ModelServers {
    private llama: ChildProcess | null = null;
    private loadedStudio: OwnedStudioModel | null = null;
    private pending: { controller: AbortController; done: Promise<void> } | null = null;

    constructor(private readonly studio: StudioRuntime = new LocalStudioRuntime()) {}

    load(profile: ModelProfile): Promise<void> {
        const previous = this.stop();
        const controller = new AbortController();
        const pending = { controller, done: Promise.resolve() };
        this.pending = pending;
        pending.done = (async () => {
            await previous;
            const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(240000)]);
            signal.throwIfAborted();
            await this.loadProfile(profile, signal);
            signal.throwIfAborted();
        })().catch(async (error: unknown) => {
            await this.releaseOwned();
            throw error;
        });
        return pending.done.finally(() => {
            if (this.pending === pending) this.pending = null;
        });
    }

    private async loadProfile(profile: ModelProfile, signal: AbortSignal): Promise<void> {
        if (profile.runtime === "lm-studio") {
            this.loadedStudio = await this.studio.load(profile, signal);
            return;
        }
        // An existing endpoint is usable only if it already serves this exact configured model.
        const existing = await fetch(`${profile.baseUrl}/models`, {
            headers: { authorization: `Bearer ${profile.apiKey}` },
            signal: AbortSignal.any([signal, AbortSignal.timeout(1000)]),
        })
            .then((response) => (response.ok ? (response.json() as Promise<{ data?: { id: string }[] }>) : null))
            .catch(() => null);
        signal.throwIfAborted();
        if (existing?.data?.some((model) => model.id === profile.model_id)) return;
        this.llama = spawn(
            profile.executable,
            [
                "--model",
                profile.modelPath,
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
                "--ctx-size",
                String(profile.context_limit_tokens),
                "--parallel",
                "1",
                "--jinja",
                "--alias",
                profile.model_id,
                "--api-key",
                profile.apiKey,
            ],
            { stdio: "ignore", windowsHide: true },
        );
        let failed = false;
        this.llama.once("error", () => {
            failed = true;
        });
        this.llama.once("exit", () => {
            failed = true;
        });
        const deadline = Date.now() + 240000;
        while (Date.now() < deadline && !failed) {
            signal.throwIfAborted();
            const response = await fetch("http://127.0.0.1:8080/health", {
                headers: { authorization: `Bearer ${profile.apiKey}` },
                signal: AbortSignal.any([signal, AbortSignal.timeout(1000)]),
            }).catch(() => null);
            if (response?.ok) return;
            await delay(500, undefined, { signal });
        }
        throw new Error("local model server did not become ready");
    }

    async stop(): Promise<void> {
        const pending = this.pending;
        this.pending = null;
        pending?.controller.abort(new Error("model load stopped"));
        await pending?.done.catch(() => {});
        await this.releaseOwned();
    }

    private async releaseOwned(): Promise<void> {
        const child = this.llama;
        this.llama = null;
        if (child && child.exitCode === null) {
            child.kill("SIGTERM");
            await Promise.race([new Promise<void>((resolve) => child.once("exit", () => resolve())), delay(4000)]);
            if (child.exitCode === null) child.kill("SIGKILL");
        }
        const studio = this.loadedStudio;
        this.loadedStudio = null;
        if (studio) await studio.stop().catch(() => {});
    }
}
