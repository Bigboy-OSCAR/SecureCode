import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { devStatePath } from "../dev/state.js";
import { WORK_ROOT } from "../lib/processes.js";
import { findFreePorts } from "../lib/services.js";

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

test("one dev launcher owns a data directory and stop waits for both ports to close", { timeout: 35000 }, async () => {
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-dev-"));
    const { hostPort, servicePort } = await findFreePorts();
    const env = {
        ...process.env,
        ANTHROPIC_API_KEY: "",
        SECURECODE_DATA_DIR: dataDir,
        SECURECODE_HOST_PORT: String(hostPort),
        SECURECODE_CONTEXT_SERVICE_PORT: String(servicePort),
    };
    const entry = ["--import", "tsx", "scripts/dev/start.ts"];
    const launcher = spawn(process.execPath, entry, { cwd: WORK_ROOT, env, stdio: "ignore" });
    const exited = new Promise<number | null>((done, reject) => {
        launcher.once("error", reject);
        launcher.once("close", done);
    });
    try {
        const deadline = Date.now() + 20000;
        const hostHealth = `http://127.0.0.1:${hostPort}/api/v1/health`;
        while (true) {
            assert.equal(launcher.exitCode, null, "launcher exited during startup");
            assert.ok(Date.now() < deadline, "dev startup timed out");
            const response = await fetch(hostHealth, { signal: AbortSignal.timeout(750) }).catch(() => undefined);
            const body: unknown = response && (await response.json());
            if (body && typeof body === "object" && "status" in body && body.status === "ok") break;
            await delay(100);
        }
        assert.equal(spawnSync(process.execPath, entry, { cwd: WORK_ROOT, env }).status, 1);
        const stop = spawnSync(process.execPath, ["--import", "tsx", "scripts/dev/stop.ts"], {
            cwd: WORK_ROOT,
            env,
            encoding: "utf8",
            timeout: 15000,
        });
        assert.equal(stop.status, 0, stop.stderr);
        assert.equal(await exited, 0);
        for (const port of [hostPort, servicePort]) {
            await assert.rejects(fetch(`http://127.0.0.1:${port}/`, { signal: AbortSignal.timeout(1000) }));
        }
    } finally {
        if (launcher.exitCode === null && launcher.signalCode === null) launcher.kill("SIGTERM");
        await exited;
        rmSync(dataDir, { recursive: true, force: true });
    }
});
