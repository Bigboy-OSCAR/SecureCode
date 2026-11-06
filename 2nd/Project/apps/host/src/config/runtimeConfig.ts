/**
 * SDK-run settings from the environment (names match the root .env.example).
 * The provider API key is returned separately and only handed to the Cline
 * adapter; it is never part of a response, a log line or the settings DTO.
 */
import { isAbsolute, resolve } from "node:path";
import { ConfigError } from "./hostConfig.js";

export interface RuntimeConfig {
    clineHome: string;
    approvalTimeoutMs: number;
    hookTimeoutMs: number;
    contextLimitTokens: number;
    maxOutputTokens: number;
    safetyMarginTokens: number;
    providerBaseUrl: string | null;
    /** One-time browser code from the launcher; null lets the host generate and print one. */
    bootstrapCode: string | null;
    /** Absolute directories a workspace root must live under; empty = any non-root directory. */
    allowedWorkspaceRoots: string[];
    commandTimeoutMs: number;
}

export interface ProviderCredentials {
    apiKey: string | null;
}

function readInteger(env: NodeJS.ProcessEnv, name: string, fallback: number, min: number, max: number): number {
    const raw = env[name]?.trim();
    if (!raw) return fallback;
    const value = Number(raw);
    if (!Number.isInteger(value) || value < min || value > max) {
        throw new ConfigError(`${name} must be an integer between ${min} and ${max}`);
    }
    return value;
}

function readBaseUrl(env: NodeJS.ProcessEnv): string | null {
    const raw = env.SECURECODE_PROVIDER_BASE_URL?.trim();
    if (!raw) return null;
    let url: URL;
    try {
        url = new URL(raw);
    } catch {
        throw new ConfigError("SECURECODE_PROVIDER_BASE_URL must be a URL");
    }
    const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
    if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) {
        throw new ConfigError("SECURECODE_PROVIDER_BASE_URL must use https (http only on loopback)");
    }
    return url.href;
}

function readBootstrapCode(env: NodeJS.ProcessEnv): string | null {
    const raw = env.SECURECODE_BOOTSTRAP_CODE?.trim();
    if (!raw) return null;
    if (!/^[A-Za-z0-9-]{16,64}$/.test(raw)) {
        throw new ConfigError("SECURECODE_BOOTSTRAP_CODE must be 16-64 characters of [A-Za-z0-9-]");
    }
    return raw;
}

function readAllowedRoots(env: NodeJS.ProcessEnv): string[] {
    const roots = (env.SECURECODE_ALLOWED_WORKSPACE_ROOTS ?? "")
        .split(",")
        .map((entry) => entry.trim())
        .filter(Boolean);
    for (const root of roots) {
        if (!isAbsolute(root)) throw new ConfigError("SECURECODE_ALLOWED_WORKSPACE_ROOTS entries must be absolute");
    }
    return roots.map((root) => resolve(root));
}

export function loadRuntimeConfig(env: NodeJS.ProcessEnv, dataDir: string): RuntimeConfig {
    const clineSetting = env.SECURECODE_CLINE_HOME?.trim();
    const contextLimitTokens = readInteger(env, "SECURECODE_MODEL_CONTEXT_LIMIT", 200000, 1024, 1000000);
    const maxOutputTokens = readInteger(env, "SECURECODE_MAX_OUTPUT_TOKENS", 8192, 1, 128000);
    if (maxOutputTokens >= contextLimitTokens) {
        throw new ConfigError("SECURECODE_MAX_OUTPUT_TOKENS must be smaller than SECURECODE_MODEL_CONTEXT_LIMIT");
    }
    return {
        clineHome: clineSetting ? resolve(clineSetting) : resolve(dataDir, "cline"),
        approvalTimeoutMs: readInteger(env, "SECURECODE_APPROVAL_TIMEOUT_MS", 300000, 100, 3600000),
        hookTimeoutMs: readInteger(env, "SECURECODE_HOOK_TIMEOUT_MS", 5000, 50, 60000),
        contextLimitTokens,
        maxOutputTokens,
        safetyMarginTokens: readInteger(env, "SECURECODE_CONTEXT_SAFETY_MARGIN_TOKENS", 2048, 0, 100000),
        providerBaseUrl: readBaseUrl(env),
        bootstrapCode: readBootstrapCode(env),
        allowedWorkspaceRoots: readAllowedRoots(env),
        commandTimeoutMs: readInteger(env, "SECURECODE_COMMAND_TIMEOUT_MS", 120000, 100, 3600000),
    };
}

export function readProviderCredentials(env: NodeJS.ProcessEnv): ProviderCredentials {
    const apiKey = env.ANTHROPIC_API_KEY?.trim();
    return { apiKey: apiKey ? apiKey : null };
}
