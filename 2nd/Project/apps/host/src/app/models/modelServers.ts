/** Owns only model processes started by this host; never stops unrelated local servers. */
import { execFile, spawn, type ChildProcess } from "node:child_process";
import { promisify } from "node:util";
import { setTimeout as delay } from "node:timers/promises";
import type { ModelProfile } from "./modelProfiles.js";

const execute = promisify(execFile);

export class ModelServers {
    private llama: ChildProcess | null = null;
    private loadedStudio: ModelProfile | null = null;

    async load(profile: ModelProfile): Promise<void> {
        await this.stop();
        if (profile.runtime === "lm-studio") {
            await execute(profile.executable, ["server", "start", "--port", "1234"], { timeout: 30000 });
            const loaded = await execute(profile.executable, ["ps", "--json"], { timeout: 10000 });
            const instances = JSON.parse(loaded.stdout) as { identifier: string; contextLength: number }[];
            if (
                instances.some(
                    (model) =>
                        model.identifier === profile.model_id && model.contextLength >= profile.context_limit_tokens,
                )
            )
                return;
            await execute(
                profile.executable,
                [
                    "load",
                    profile.model_id,
                    "--identifier",
                    profile.model_id,
                    "--context-length",
                    String(profile.context_limit_tokens),
                    "--yes",
                ],
                { timeout: 240000 },
            );
            this.loadedStudio = profile;
            return;
        }
        // An existing endpoint is usable only if it already serves this exact configured model.
        const existing = await fetch(`${profile.baseUrl}/models`, {
            headers: { authorization: `Bearer ${profile.apiKey}` },
            signal: AbortSignal.timeout(1000),
        })
            .then((response) => (response.ok ? (response.json() as Promise<{ data?: { id: string }[] }>) : null))
            .catch(() => null);
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
            const response = await fetch("http://127.0.0.1:8080/health", {
                headers: { authorization: `Bearer ${profile.apiKey}` },
                signal: AbortSignal.timeout(1000),
            }).catch(() => null);
            if (response?.ok) return;
            await delay(500);
        }
        await this.stop();
        throw new Error("local model server did not become ready");
    }

    async stop(): Promise<void> {
        const child = this.llama;
        this.llama = null;
        if (child && child.exitCode === null) {
            child.kill("SIGTERM");
            await Promise.race([new Promise<void>((resolve) => child.once("exit", () => resolve())), delay(4000)]);
            if (child.exitCode === null) child.kill("SIGKILL");
        }
        const studio = this.loadedStudio;
        this.loadedStudio = null;
        if (studio) await execute(studio.executable, ["unload", studio.model_id], { timeout: 30000 }).catch(() => {});
    }
}
