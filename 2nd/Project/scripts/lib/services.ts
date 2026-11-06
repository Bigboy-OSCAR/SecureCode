/** Own the two actual child processes, including partial-start failures. */
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync } from "node:fs";
import { createServer } from "node:net";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { SERVICE_DIR, WORK_ROOT } from "./processes.js";

interface StartOptions {
    hostPort: number;
    servicePort: number;
    dataDir: string;
    signal?: AbortSignal;
    onOutput?: (source: string, chunk: string) => void;
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

function checkPort(port: number): Promise<number> {
    return new Promise((done, reject) => {
        const socket = createServer();
        socket.once("error", reject);
        socket.listen(port, "127.0.0.1", () => {
            const address = socket.address();
            socket.close((error) => {
                if (error || !address || typeof address === "string") reject(error ?? new Error("port unavailable"));
                else done(address.port);
            });
        });
    });
}

export async function findFreePorts(): Promise<{ hostPort: number; servicePort: number }> {
    const hostPort = await checkPort(0);
    let servicePort = await checkPort(0);
    while (servicePort === hostPort) servicePort = await checkPort(0);
    return { hostPort, servicePort };
}

function launch(
    name: string,
    executable: string,
    args: string[],
    cwd: string,
    env: NodeJS.ProcessEnv,
    output: StartOptions["onOutput"],
) {
    const child = spawn(executable, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    for (const stream of [child.stdout, child.stderr]) {
        stream.setEncoding("utf8");
        stream.on("data", (chunk: string) => output?.(name, chunk));
    }
    let ended = false;
    const closed = new Promise<void>((done) => {
        child.once("error", () => {
            ended = true;
        });
        child.once("close", () => {
            ended = true;
            done();
        });
    });
    let stopping: Promise<void> | undefined;
    function stop(): Promise<void> {
        if (!stopping)
            stopping = (async () => {
                if (!ended && child.exitCode === null && child.signalCode === null) {
                    child.kill("SIGTERM");
                    const force = setTimeout(() => child.kill("SIGKILL"), 5000);
                    try {
                        await closed;
                    } finally {
                        clearTimeout(force);
                    }
                } else await closed;
            })();
        return stopping;
    }
    return { child, stop, exited: () => ended || child.exitCode !== null || child.signalCode !== null };
}

export async function startServices(options: StartOptions): Promise<Services> {
    const { hostPort, servicePort, dataDir, signal, onOutput } = options;
    if (hostPort === servicePort || [hostPort, servicePort].some((p) => !Number.isInteger(p) || p < 1 || p > 65535)) {
        throw new Error("host and context-service need distinct ports in 1..65535");
    }
    await Promise.all([checkPort(hostPort), checkPort(servicePort)]);
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
    const service = launch("context-service", python, ["-m", "securecode_context.app"], SERVICE_DIR, env, onOutput);
    const host = launch(
        "host",
        process.execPath,
        ["--import", "tsx", "apps/host/src/app/main.ts"],
        WORK_ROOT,
        env,
        onOutput,
    );
    const hostUrl = `http://127.0.0.1:${hostPort}`;
    const serviceUrl = `http://127.0.0.1:${servicePort}`;
    const stopAll = async (): Promise<void> => {
        await Promise.all([host.stop(), service.stop()]);
    };
    try {
        const deadline = Date.now() + 20000;
        while (Date.now() < deadline) {
            signal?.throwIfAborted();
            if (host.exited() || service.exited()) throw new Error("a server exited during startup");
            try {
                const response = await fetch(hostUrl + "/api/v1/health", {
                    signal: AbortSignal.timeout(1000),
                    redirect: "error",
                });
                const body: unknown = await response.json();
                if (response.ok && body && typeof body === "object" && "status" in body && body.status === "ok") {
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
                }
            } catch {
                /* Health is retried while both child processes are starting. */
            }
            await delay(100);
        }
        throw new Error("servers did not become healthy within 20 seconds");
    } catch (error) {
        await stopAll();
        throw error;
    }
}
