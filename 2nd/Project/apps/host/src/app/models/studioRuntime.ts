/** LM Studio's official load cancellation; only a handle created here is owned. */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { LMStudioClient } from "@lmstudio/sdk";
import type { ModelProfile } from "./modelProfiles.js";

const execute = promisify(execFile);

export interface OwnedStudioModel {
    stop(): Promise<void>;
}
export interface StudioRuntime {
    load(profile: ModelProfile, signal: AbortSignal): Promise<OwnedStudioModel | null>;
}

export class LocalStudioRuntime implements StudioRuntime {
    async load(profile: ModelProfile, signal: AbortSignal): Promise<OwnedStudioModel | null> {
        await execute(profile.executable, ["server", "start", "--port", "1234"], { timeout: 30000, signal });
        const loaded = await execute(profile.executable, ["ps", "--json"], { timeout: 10000, signal });
        const instances = JSON.parse(loaded.stdout) as { identifier: string; contextLength: number }[];
        if (
            instances.some(
                (model) => model.identifier === profile.model_id && model.contextLength >= profile.context_limit_tokens,
            )
        ) {
            return null;
        }
        signal.throwIfAborted();
        const client = new LMStudioClient({
            baseUrl: "ws://127.0.0.1:1234",
            logger: { info() {}, warn() {}, error() {}, debug() {} },
        });
        try {
            const model = await client.llm.load(profile.modelPath, {
                identifier: profile.model_id,
                config: { contextLength: profile.context_limit_tokens },
                deviceIdentifier: null,
                signal,
                verbose: false,
            });
            return {
                async stop() {
                    try {
                        await model.unload();
                    } finally {
                        await client[Symbol.asyncDispose]();
                    }
                },
            };
        } catch (error) {
            // AbortSignal sends the load channel's cancel message before closing the connection.
            await client[Symbol.asyncDispose]();
            throw error;
        }
    }
}
