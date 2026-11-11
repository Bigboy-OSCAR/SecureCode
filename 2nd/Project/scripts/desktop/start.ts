/** Native app child: starts local services and reports bootstrap credentials only through its private pipe. */
import { once } from "node:events";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { devDataDir, claimInstance, releaseInstance, stopRequestPath } from "../dev/state.js";
import { startServices, type Services } from "../lib/services.js";
import { findFreePorts } from "../lib/ports.js";
import { WORK_ROOT } from "../lib/processes.js";
import { startDesktopUi } from "./uiServer.js";

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
const stopWatch = setInterval(() => {
    if (dataDir && instance && existsSync(stopRequestPath(dataDir, instance))) controller.abort();
}, 150);
try {
    dataDir = devDataDir();
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
    await ui?.stop();
    await services?.stopAll();
    if (dataDir && instance) releaseInstance(dataDir, instance);
}
