/** Own the context-service and host processes in readiness order, including partial-start failures. */
import type { ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { launch, type LaunchedChild, type OutputSink } from "./childProcess.js";
import { checkPort } from "./ports.js";
import { SERVICE_DIR, WORK_ROOT } from "./processes.js";
import { jsonStatusOk, waitReady } from "./readiness.js";

export { findFreePorts } from "./ports.js";

interface StartOptions {
    hostPort: number;
    servicePort: number;
    dataDir: string;
    signal?: AbortSignal;
    onOutput?: OutputSink;
}
export interface Services {
    host: ChildProcess;
    service: ChildProcess;
    hostUrl: string;
    serviceUrl: string;
    internalToken: string;
    /** One-time browser launch code (POST /api/v1/auth/bootstrap); shown on the local terminal only. */
    bootstrapCode: string;
    stopService(): Promise<void>;
    stopAll(): Promise<void>;
}

export async function startServices(options: StartOptions): Promise<Services> {
    const { hostPort, servicePort, dataDir, signal, onOutput } = options;
    if (hostPort === servicePort || [hostPort, servicePort].some((p) => !Number.isInteger(p) || p < 1 || p > 65535)) {
        throw new Error("host and context-service need distinct ports in 1..65535");
    }
    await checkPort(hostPort, "SECURECODE_HOST_PORT");
    await checkPort(servicePort, "SECURECODE_CONTEXT_SERVICE_PORT");
    // Spawn the interpreter itself so stopping the launcher cannot orphan an uv child.
    const venv = resolve(SERVICE_DIR, process.env.UV_PROJECT_ENVIRONMENT || ".venv");
    const python = join(venv, process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
    if (!existsSync(python))
        throw new Error("context-service environment missing: run uv sync --frozen in services/context-service");
    mkdirSync(join(dataDir, "run"), { recursive: true, mode: 0o700 });
    const internalToken = randomBytes(32).toString("hex");
    const bootstrapCode = randomBytes(18).toString("base64url").replaceAll("_", "-");
    const env = {
        ...process.env,
        SECURECODE_INTERNAL_TOKEN: internalToken,
        SECURECODE_BOOTSTRAP_CODE: bootstrapCode,
        SECURECODE_DATA_DIR: dataDir,
        SECURECODE_CONTEXT_SERVICE_HOST: "127.0.0.1",
        SECURECODE_HOST_PORT: String(hostPort),
        SECURECODE_CONTEXT_SERVICE_PORT: String(servicePort),
        SECURECODE_CLINE_HOME: process.env.SECURECODE_CLINE_HOME || join(dataDir, "cline"),
    };
    signal?.throwIfAborted();
    const hostUrl = `http://127.0.0.1:${hostPort}`;
    const serviceUrl = `http://127.0.0.1:${servicePort}`;
    // Readiness order: the context-service must answer its authenticated health before the host starts.
    const service = launch("context-service", python, ["-m", "securecode_context.app"], SERVICE_DIR, env, onOutput);
    let host: LaunchedChild | undefined;
    const stopAll = async (): Promise<void> => {
        await Promise.all([host?.stop(), service.stop()]);
    };
    try {
        await waitReady(
            {
                name: "context-service",
                url: serviceUrl + "/internal/v1/health",
                headers: { authorization: `Bearer ${internalToken}` },
                ready: jsonStatusOk,
            },
            service,
            30000,
            signal,
        );
        host = launch(
            "host",
            process.execPath,
            ["--import", "tsx", "apps/host/src/app/main.ts"],
            WORK_ROOT,
            env,
            onOutput,
        );
        await waitReady({ name: "host", url: hostUrl + "/api/v1/health", ready: jsonStatusOk }, host, 30000, signal);
        return {
            host: host.child,
            service: service.child,
            internalToken,
            bootstrapCode,
            hostUrl,
            serviceUrl,
            stopAll,
            stopService: service.stop,
        };
    } catch (error) {
        await stopAll();
        throw error;
    }
}
