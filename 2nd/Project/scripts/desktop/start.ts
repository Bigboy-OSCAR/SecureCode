/** Native app child: starts local services and reports bootstrap credentials only through its private pipe. */
import { once } from "node:events";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { claimInstance, releaseInstance, stopRequestPath } from "../dev/state.js";
import { startServices, type Services } from "../lib/services.js";
import { findFreePorts } from "../lib/ports.js";
import { WORK_ROOT } from "../lib/processes.js";
import { startDesktopUi } from "./uiServer.js";
import { desktopDataDir } from "./dataDirectory.js";

const controller = new AbortController();
for (const signal of ["SIGTERM", "SIGINT", "SIGHUP"] as const) {
    process.once(signal, () => controller.abort());
}
const parentPid = process.ppid;
const parentWatch = setInterval(() => {
    try {
        process.kill(parentPid, 0);
    } catch {
        controller.abort();
    }
}, 1000);

let services: Services | undefined;
let ui: Awaited<ReturnType<typeof startDesktopUi>> | undefined;
let instance: string | undefined;
let dataDir: string | undefined;
const input = createInterface({ input: process.stdin });
let authenticating = false;
input.on("line", (line: string) => {
    if (line !== '{"reauthenticate":true}' || authenticating || !services || !ui) return;
    authenticating = true;
    const current = services;
    void (async () => {
        const response = await fetch(`${current.hostUrl}/api/v1/auth/launch-code`, {
            method: "POST",
            headers: { authorization: `Bearer ${current.internalToken}`, origin: current.hostUrl },
            signal: AbortSignal.timeout(15000),
        });
        const data: unknown = await response.json();
        if (!response.ok || !data || typeof data !== "object" || !("code" in data) || typeof data.code !== "string") {
            throw new Error("Could not renew local authentication.");
        }
        process.stdout.write(JSON.stringify({ ready: true, url: ui?.url, code: data.code }) + "\n");
    })()
        .catch(() => {
            process.stdout.write(
                JSON.stringify({ error: "로컬 인증을 갱신하지 못했습니다. 앱을 다시 실행해 주세요." }) + "\n",
            );
        })
        .finally(() => {
            authenticating = false;
        });
});
const stopWatch = setInterval(() => {
    if (dataDir && instance && existsSync(stopRequestPath(dataDir, instance))) controller.abort();
}, 150);
try {
    dataDir = desktopDataDir();
    instance = claimInstance(dataDir);
    const ports = await findFreePorts();
    // The host permits this exact UI origin, even when the developer ports are occupied.
    process.env.SECURECODE_UI_DEV_PORT = String(ports.uiPort);
    services = await startServices({ ...ports, dataDir, signal: controller.signal });
    ui = await startDesktopUi({ ...ports, directory: join(WORK_ROOT, "apps", "ui", "dist") });
    process.stdout.write(JSON.stringify({ ready: true, url: ui.url, code: services.bootstrapCode }) + "\n");
    if (!controller.signal.aborted) {
        await Promise.race([
            once(controller.signal, "abort"),
            ...[services.host, services.service].map(async (child) => {
                await once(child, "exit");
                if (!controller.signal.aborted) throw new Error("A local service stopped unexpectedly.");
            }),
        ]);
    }
} catch (error) {
    if (!controller.signal.aborted) {
        process.stdout.write(
            JSON.stringify({ error: error instanceof Error ? error.message : "LocalDesk could not start." }) + "\n",
        );
        process.exitCode = 1;
    }
} finally {
    controller.abort();
    clearInterval(parentWatch);
    clearInterval(stopWatch);
    input.close();
    await ui?.stop();
    await services?.stopAll();
    if (dataDir && instance) releaseInstance(dataDir, instance);
}
