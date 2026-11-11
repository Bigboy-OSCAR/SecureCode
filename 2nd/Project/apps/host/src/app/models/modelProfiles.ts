/** Trusted local configuration; browser model IDs never become executable paths. */
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import type { LocalModel } from "@securecode/contracts";

export interface ModelProfile extends LocalModel {
    baseUrl: string;
    modelPath: string;
    executable: string;
    apiKey: string;
}

export function localModelProfiles(env: NodeJS.ProcessEnv, workRoot: string): ModelProfile[] {
    const llamaPath = resolve(
        env.SECURECODE_LLAMA_MODEL_PATH ||
            join(
                workRoot,
                ".securecode/models/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
            ),
    );
    const llamaBin = env.SECURECODE_LLAMA_SERVER_BIN || "/opt/homebrew/bin/llama-server";
    const studioPath = env.SECURECODE_STUDIO_MODEL_PATH || "lmstudio-community/Qwen3.8-27B-MLX-5bit";
    const studioBin = env.SECURECODE_STUDIO_BIN || join(homedir(), ".lmstudio/bin/lms");
    const context = Number(env.SECURECODE_MODEL_CONTEXT_LIMIT || 32768);
    return [
        {
            model_id: "qwen3.8-27b-mlx",
            display_name: "Qwen 3.8 · 27B",
            runtime: "lm-studio",
            context_limit_tokens: context,
            available: existsSync(join(homedir(), ".lmstudio/models", studioPath)) && existsSync(studioBin),
            baseUrl: "http://127.0.0.1:1234/v1",
            modelPath: studioPath,
            executable: studioBin,
            apiKey: env.SECURECODE_STUDIO_API_KEY || randomBytes(24).toString("hex"),
        },
        {
            model_id: "qwen2.5-7b-instruct",
            display_name: "Qwen 2.5 · 7B",
            runtime: "llama-cpp",
            context_limit_tokens: context,
            available: existsSync(llamaPath) && existsSync(llamaBin),
            baseUrl: "http://127.0.0.1:8080/v1",
            modelPath: llamaPath,
            executable: llamaBin,
            apiKey: env.SECURECODE_PROVIDER_API_KEY || randomBytes(24).toString("hex"),
        },
    ];
}
