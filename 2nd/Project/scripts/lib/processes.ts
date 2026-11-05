import { spawn, spawnSync } from "node:child_process";
import { join, resolve } from "node:path";
import type { StepResult } from "./report.js";

export const WORK_ROOT = resolve(import.meta.dirname, "..", "..");
export const SERVICE_DIR = join(WORK_ROOT, "services", "context-service");

export function nodeBin(relativeScript: string): [string, string] {
    return [process.execPath, join(WORK_ROOT, "node_modules", relativeScript)];
}

export function uvCommand(): string {
    return process.env.UV_BIN?.trim() || "uv";
}

export function isUvAvailable(): boolean {
    return spawnSync(uvCommand(), ["--version"], { stdio: "ignore" }).status === 0;
}

export function toolStep(
    name: string,
    executable: string,
    args: string[],
    options: { cwd?: string; knownExit?: number; ownerTask?: string } = {},
): Promise<StepResult> {
    return new Promise((done) => {
        const child = spawn(executable, args, { cwd: options.cwd ?? WORK_ROOT, stdio: "inherit" });
        child.once("error", (error) => done({ name, status: "FAIL", detail: error.message }));
        child.once("close", (code, signal) => {
            const known = code !== null && code === options.knownExit;
            done({
                name,
                status: code === 0 ? "PASS" : known ? "KNOWN" : "FAIL",
                detail: code === 0 ? "ok" : (signal ?? `exit ${code}`),
                ownerTask: known ? options.ownerTask : undefined,
            });
        });
    });
}

export function uvStep(name: string, args: string[], knownExit?: number, ownerTask?: string): Promise<StepResult> {
    return toolStep(name, uvCommand(), ["run", "--frozen", ...args], { cwd: SERVICE_DIR, knownExit, ownerTask });
}
