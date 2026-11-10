import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { createServer } from "node:net";
import { devStatePath } from "../dev/state.js";
import { startStack } from "../lib/devStack.js";
import { WORK_ROOT } from "../lib/processes.js";
import { findFreePorts } from "../lib/ports.js";

test("stop refuses a legacy or malformed pid record", () => {
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-stop-"));
    try {
        mkdirSync(join(dataDir, "run"));
        // Deliberately omit PIDs: even an old stop executable cannot signal an unrelated process.
        const state = JSON.stringify({ host_port: 8787, service_port: 8788 });
        writeFileSync(devStatePath(dataDir), state);
        const result = spawnSync(process.execPath, ["--import", "tsx", "scripts/dev/stop.ts"], {
            cwd: WORK_ROOT,
            env: { ...process.env, SECURECODE_DATA_DIR: dataDir },
            encoding: "utf8",
        });
        assert.equal(result.status, 1);
        assert.match(result.stderr, /old dev-processes/);
        assert.equal(readFileSync(devStatePath(dataDir), "utf8"), state);
    } finally {
        rmSync(dataDir, { recursive: true, force: true });
    }
});

function devEnv(dataDir: string, ports: { hostPort: number; servicePort: number; uiPort: number }) {
    return {
        ...process.env,
        ANTHROPIC_API_KEY: "",
        SECURECODE_DATA_DIR: dataDir,
        SECURECODE_HOST_PORT: String(ports.hostPort),
        SECURECODE_CONTEXT_SERVICE_PORT: String(ports.servicePort),
        SECURECODE_UI_DEV_PORT: String(ports.uiPort),
    };
}

async function assertClosed(ports: number[]): Promise<void> {
    for (const port of ports) {
        await assert.rejects(fetch(`http://127.0.0.1:${port}/`, { signal: AbortSignal.timeout(1000) }), `port ${port}`);
    }
}

test(
    "one dev launcher owns a data directory, serves the UI and stop closes all three ports",
    { timeout: 90000 },
    async () => {
        const dataDir = mkdtempSync(join(tmpdir(), "securecode-dev-"));
        const ports = await findFreePorts();
        const { hostPort, servicePort, uiPort } = ports;
        const env = devEnv(dataDir, ports);
        const entry = ["--import", "tsx", "scripts/dev/start.ts"];
        const launcher = spawn(process.execPath, entry, { cwd: WORK_ROOT, env, stdio: "ignore" });
        const exited = new Promise<number | null>((done, reject) => {
            launcher.once("error", reject);
            launcher.once("close", done);
        });
        try {
            const deadline = Date.now() + 70000;
            // The UI is started last, so its index page means the whole stack is up.
            while (true) {
                assert.equal(launcher.exitCode, null, "launcher exited during startup");
                assert.ok(Date.now() < deadline, "dev startup timed out");
                const page = await fetch(`http://127.0.0.1:${uiPort}/`, { signal: AbortSignal.timeout(750) })
                    .then((response) => response.text())
                    .catch(() => "");
                if (page.includes('id="root"')) break;
                await delay(200);
            }
            const proxied = await fetch(`http://127.0.0.1:${uiPort}/api/v1/health`);
            assert.equal(((await proxied.json()) as { status?: string }).status, "ok", "UI proxies /api to the host");
            assert.equal(spawnSync(process.execPath, entry, { cwd: WORK_ROOT, env }).status, 1);
            const stop = spawnSync(process.execPath, ["--import", "tsx", "scripts/dev/stop.ts"], {
                cwd: WORK_ROOT,
                env,
                encoding: "utf8",
                timeout: 15000,
            });
            assert.equal(stop.status, 0, stop.stderr);
            assert.equal(await exited, 0);
            await assertClosed([hostPort, servicePort, uiPort]);
        } finally {
            if (launcher.exitCode === null && launcher.signalCode === null) launcher.kill("SIGTERM");
            await exited;
            rmSync(dataDir, { recursive: true, force: true });
        }
    },
);

test("a port conflict fails before any server starts and names the setting", { timeout: 30000 }, async () => {
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-port-"));
    const ports = await findFreePorts();
    const blocker = createServer();
    await new Promise<void>((done) => blocker.listen(ports.hostPort, "127.0.0.1", done));
    try {
        const result = spawnSync(process.execPath, ["--import", "tsx", "scripts/dev/start.ts"], {
            cwd: WORK_ROOT,
            env: devEnv(dataDir, ports),
            encoding: "utf8",
            timeout: 25000,
        });
        assert.equal(result.status, 1, result.stderr);
        assert.match(result.stderr, /already in use \(SECURECODE_HOST_PORT\)/);
        await assertClosed([ports.servicePort, ports.uiPort]);
        assert.throws(() => readFileSync(devStatePath(dataDir)), "launcher released its instance record");
    } finally {
        blocker.close();
        rmSync(dataDir, { recursive: true, force: true });
    }
});

test("a UI start failure stops the context-service and host already started", { timeout: 60000 }, async () => {
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-partial-"));
    const ports = await findFreePorts();
    let healthyBeforeFailure = false;
    try {
        await assert.rejects(
            startStack({
                ...ports,
                dataDir,
                uiStarter: async () => {
                    const health = await fetch(`http://127.0.0.1:${ports.hostPort}/api/v1/health`);
                    healthyBeforeFailure = ((await health.json()) as { status?: string }).status === "ok";
                    throw new Error("ui failed to start");
                },
            }),
            /ui failed to start/,
        );
        assert.ok(healthyBeforeFailure, "UI starts only after the host is healthy");
        await assertClosed([ports.hostPort, ports.servicePort]);
    } finally {
        rmSync(dataDir, { recursive: true, force: true });
    }
});
