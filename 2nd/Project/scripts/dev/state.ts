/** Stop requests address one launcher instance, never a PID read from disk. */
import { existsSync, linkSync, mkdirSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { join, resolve } from "node:path";
import { WORK_ROOT } from "../lib/processes.js";

export function devDataDir(): string {
    const envFile = join(WORK_ROOT, ".env");
    if (existsSync(envFile)) process.loadEnvFile(envFile);
    return resolve(WORK_ROOT, process.env.SECURECODE_DATA_DIR?.trim() || ".securecode");
}

export function devStatePath(dataDir: string): string {
    return join(dataDir, "run", "dev-processes.json");
}

export function claimInstance(dataDir: string): string {
    mkdirSync(join(dataDir, "run"), { recursive: true, mode: 0o700 });
    const instance = randomUUID();
    const statePath = devStatePath(dataDir);
    const staged = statePath + "." + instance;
    writeFileSync(staged, JSON.stringify({ instance, launcher_pid: process.pid }), { flag: "wx", mode: 0o600 });
    try {
        // Link only a complete record; two launchers cannot publish over one another.
        linkSync(staged, statePath);
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "EEXIST")
            throw new Error("dev state already exists; run npm run stop first", { cause: error });
        throw error;
    } finally {
        unlinkSync(staged);
    }
    return instance;
}

export function currentInstance(dataDir: string): { instance: string; launcherPid: number } | undefined {
    let text: string;
    try {
        text = readFileSync(devStatePath(dataDir), "utf8");
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
        throw error;
    }
    const state: unknown = JSON.parse(text);
    if (
        !state ||
        typeof state !== "object" ||
        !("instance" in state) ||
        typeof state.instance !== "string" ||
        !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(state.instance) ||
        !("launcher_pid" in state) ||
        typeof state.launcher_pid !== "number" ||
        !Number.isSafeInteger(state.launcher_pid) ||
        state.launcher_pid <= 1
    ) {
        throw new Error(
            "invalid or old dev-processes.json; inspect the running servers before removing the stale record",
        );
    }
    return { instance: state.instance, launcherPid: state.launcher_pid };
}

export function stopRequestPath(dataDir: string, instance: string): string {
    return join(dataDir, "run", `stop-${instance}`);
}

export function releaseInstance(dataDir: string, instance: string): void {
    if (currentInstance(dataDir)?.instance !== instance) return;
    const request = stopRequestPath(dataDir, instance);
    rmSync(request, { force: true });
    unlinkSync(devStatePath(dataDir));
}
