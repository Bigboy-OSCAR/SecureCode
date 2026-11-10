/**
 * Steps of `npm run test:install` (3.7): a copy of the work tree in a new temporary directory is installed
 * from the lockfiles, started with a fresh data directory, stopped, restarted (state must survive) and
 * stopped again. The user's checkout, node_modules and .securecode are never touched.
 */
import { execFileSync, spawn, spawnSync, type ChildProcess } from "node:child_process";

import { copyFileSync, mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { findFreePorts } from "./ports.js";
import { uvCommand, WORK_ROOT } from "./processes.js";
import type { StepResult } from "./report.js";

export interface InstallCopy {
    root: string;
    env: NodeJS.ProcessEnv;
    ports: { hostPort: number; servicePort: number; uiPort: number };
}

const step = (name: string, passed: boolean, detail: string): StepResult => ({
    name,
    status: passed ? "PASS" : "FAIL",
    detail,
});

/** Copies tracked and untracked-but-not-ignored files only: no node_modules, .venv, .env or .securecode. */
export async function copyWorkTree(): Promise<InstallCopy> {
    const root = mkdtempSync(join(tmpdir(), "securecode-install-"));
    const listing = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "."], {
        cwd: WORK_ROOT,
        encoding: "utf8",
    });
    for (const path of listing.split("\0").filter(Boolean)) {
        mkdirSync(dirname(join(root, path)), { recursive: true });
        try {
            copyFileSync(join(WORK_ROOT, path), join(root, path));
        } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; // deleted in the worktree
        }
    }
    const ports = await findFreePorts();
    const env: NodeJS.ProcessEnv = {
        ...process.env,
        ANTHROPIC_API_KEY: "",
        SECURECODE_PROVIDER_API_KEY: "",
        SECURECODE_DATA_DIR: join(root, "fresh-data"),
        SECURECODE_HOST_PORT: String(ports.hostPort),
        SECURECODE_CONTEXT_SERVICE_PORT: String(ports.servicePort),
        SECURECODE_UI_DEV_PORT: String(ports.uiPort),
    };
    delete env.UV_PROJECT_ENVIRONMENT; // the copy gets its own services/context-service/.venv
    return { root, env, ports };
}

export function installSteps(copy: InstallCopy): StepResult[] {
    const shell = process.platform === "win32";
    const npm = spawnSync("npm", ["ci", "--no-audit", "--no-fund"], {
        cwd: copy.root,
        env: copy.env,
        shell,
        stdio: "inherit",
    });
    const npmOk = step("install: npm ci (package-lock.json)", npm.status === 0, `exit ${npm.status}`);
    const uv = spawnSync(uvCommand(), ["sync", "--locked"], {
        cwd: join(copy.root, "services", "context-service"),
        env: copy.env,
        stdio: "inherit",
    });
    return [npmOk, step("install: uv sync --locked (uv.lock)", uv.status === 0, `exit ${uv.status}`)];
}

/** Starts `npm run dev` in the copy and resolves with the launch code once the UI page is served. */
export async function startDev(copy: InstallCopy): Promise<{ launcher: ChildProcess; code: string }> {
    const launcher = spawn(process.execPath, ["--import", "tsx", "scripts/dev/start.ts"], {
        cwd: copy.root,
        env: copy.env,
        stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    for (const stream of [launcher.stdout, launcher.stderr])
        stream.on("data", (chunk: Buffer) => (output += chunk.toString("utf8")));
    const deadline = Date.now() + 120000;
    while (Date.now() < deadline) {
        if (launcher.exitCode !== null) throw new Error(`dev exited during startup: ${output.slice(-800)}`);
        const code = /Launch code[^:]*: (\S+)/.exec(output)?.[1];
        if (code) return { launcher, code };
        await delay(250);
    }
    launcher.kill("SIGTERM");
    throw new Error("dev did not report readiness within 120 seconds");
}

export function stopDev(copy: InstallCopy): number | null {
    return spawnSync(process.execPath, ["--import", "tsx", "scripts/dev/stop.ts"], {
        cwd: copy.root,
        env: copy.env,
        timeout: 30000,
    }).status;
}

/** Logs in through the UI origin (Vite /api proxy) and returns the session cookie. */
export async function login(copy: InstallCopy, code: string): Promise<string> {
    const ui = `http://127.0.0.1:${copy.ports.uiPort}`;
    const response = await fetch(`${ui}/api/v1/auth/bootstrap`, {
        method: "POST",
        headers: { origin: ui, "content-type": "application/json" },
        body: JSON.stringify({ code }),
    });
    if (response.status !== 200) throw new Error(`bootstrap through the UI proxy: HTTP ${response.status}`);
    return (response.headers.get("set-cookie") ?? "").split(";", 1)[0] ?? "";
}

export async function api(
    copy: InstallCopy,
    cookie: string,
    method: string,
    path: string,
    body?: unknown,
): Promise<{ status: number; body: unknown }> {
    const ui = `http://127.0.0.1:${copy.ports.uiPort}`;
    const response = await fetch(`${ui}${path}`, {
        method,
        headers: { origin: ui, cookie, "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    return { status: response.status, body: await response.json() };
}

export async function portsClosed(copy: InstallCopy): Promise<boolean> {
    for (const port of Object.values(copy.ports)) {
        const open = await fetch(`http://127.0.0.1:${port}/`, { signal: AbortSignal.timeout(1000) }).then(
            () => true,
            () => false,
        );
        if (open) return false;
    }
    return true;
}

export { step };
