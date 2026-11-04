/**
 * Host configuration from environment variables (names match the root .env.example).
 * Enforces loopback binding and a launcher-generated internal token.
 */
import { isAbsolute, resolve } from "node:path";

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface HostConfig {
    host: "127.0.0.1";
    port: number;
    contextServiceUrl: string;
    internalToken: string;
    dataDir: string;
    allowedOrigins: string[];
    allowedHosts: string[];
    logLevel: LogLevel;
    providerId: string;
    modelId: string;
    providerConfigured: boolean;
}

export class ConfigError extends Error {
    constructor(message: string) {
        super(message);
        this.name = "ConfigError";
    }
}

const MIN_INTERNAL_TOKEN_CHARS = 32;
const LOG_LEVELS: readonly LogLevel[] = ["debug", "info", "warn", "error"];
const LOOPBACK_HOSTNAMES = ["127.0.0.1", "localhost", "[::1]"];

function readPort(env: NodeJS.ProcessEnv, name: string, fallback: number): number {
    const raw = env[name]?.trim();
    if (!raw) {
        return fallback;
    }
    const port = Number(raw);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
        throw new ConfigError(`${name} must be an integer between 1 and 65535`);
    }
    return port;
}

function readLogLevel(env: NodeJS.ProcessEnv): LogLevel {
    const raw = (env.SECURECODE_LOG_LEVEL ?? "info").trim().toLowerCase() || "info";
    const level = LOG_LEVELS.find((candidate) => candidate === raw);
    if (!level) {
        throw new ConfigError(`SECURECODE_LOG_LEVEL must be one of ${LOG_LEVELS.join(", ")}`);
    }
    return level;
}

function readExtraOrigins(env: NodeJS.ProcessEnv): string[] {
    const origins = (env.SECURECODE_ALLOWED_ORIGINS ?? "")
        .split(",")
        .map((origin) => origin.trim())
        .filter(Boolean);
    for (const origin of origins) {
        let url: URL;
        try {
            url = new URL(origin);
        } catch {
            throw new ConfigError("SECURECODE_ALLOWED_ORIGINS contains an invalid origin");
        }
        if (!LOOPBACK_HOSTNAMES.includes(url.hostname) || url.origin !== origin) {
            throw new ConfigError("SECURECODE_ALLOWED_ORIGINS may only list loopback origins (scheme://host:port)");
        }
    }
    return origins;
}

export function loadHostConfig(env: NodeJS.ProcessEnv, workRoot: string): HostConfig {
    const port = readPort(env, "SECURECODE_HOST_PORT", 8787);
    const servicePort = readPort(env, "SECURECODE_CONTEXT_SERVICE_PORT", 8788);
    const uiPort = readPort(env, "SECURECODE_UI_DEV_PORT", 5173);

    const internalToken = env.SECURECODE_INTERNAL_TOKEN ?? "";
    if (internalToken.length < MIN_INTERNAL_TOKEN_CHARS) {
        throw new ConfigError(`SECURECODE_INTERNAL_TOKEN must be at least ${MIN_INTERNAL_TOKEN_CHARS} characters`);
    }

    const dataDirSetting = env.SECURECODE_DATA_DIR?.trim() || ".securecode";
    const dataDir = isAbsolute(dataDirSetting) ? dataDirSetting : resolve(workRoot, dataDirSetting);
    const hostOrigins = [`http://127.0.0.1:${port}`, `http://localhost:${port}`];
    const uiOrigins = [`http://127.0.0.1:${uiPort}`, `http://localhost:${uiPort}`];

    return {
        host: "127.0.0.1",
        port,
        contextServiceUrl: `http://127.0.0.1:${servicePort}`,
        internalToken,
        dataDir,
        allowedOrigins: [...hostOrigins, ...uiOrigins, ...readExtraOrigins(env)],
        allowedHosts: [`127.0.0.1:${port}`, `localhost:${port}`],
        logLevel: readLogLevel(env),
        providerId: env.SECURECODE_PROVIDER_ID?.trim() || "anthropic",
        modelId: env.SECURECODE_MODEL_ID?.trim() || "claude-sonnet-5-5",
        providerConfigured: Boolean(env.ANTHROPIC_API_KEY?.trim()),
    };
}
