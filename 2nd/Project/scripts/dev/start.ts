import { existsSync } from "node:fs";
import { once } from "node:events";
import { startServices, type Services } from "../lib/services.js";
import { claimInstance, devDataDir, releaseInstance, stopRequestPath } from "./state.js";

const dataDir = devDataDir();
const instance = claimInstance(dataDir);
const controller = new AbortController();
const shutdown = (): void => controller.abort();
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
const checkStop = setInterval(() => {
    if (existsSync(stopRequestPath(dataDir, instance))) shutdown();
}, 150);

let services: Services | undefined;
try {
    services = await startServices({
        hostPort: Number(process.env.SECURECODE_HOST_PORT?.trim() || 8787),
        servicePort: Number(process.env.SECURECODE_CONTEXT_SERVICE_PORT?.trim() || 8788),
        dataDir,
        signal: controller.signal,
        onOutput: (source, chunk) => process.stdout.write(`[${source}] ${chunk}`),
    });
    console.log(
        `SecureCode host: ${services.hostUrl}/api/v1/health. Launch code (single use, 10 min): ${services.bootstrapCode}. ` +
            "Web UI is pending (1.1). Ctrl+C or npm run stop to stop.",
    );
    if (!controller.signal.aborted) {
        for (const child of [services.host, services.service]) {
            if (child.exitCode !== null || child.signalCode !== null) throw new Error("server exited");
        }
        await Promise.race([
            once(controller.signal, "abort"),
            ...[services.host, services.service].map(async (child) => {
                await once(child, "exit");
                throw new Error("server exited unexpectedly");
            }),
        ]);
    }
} catch (error) {
    if (!controller.signal.aborted) throw error;
} finally {
    clearInterval(checkStop);
    await services?.stopAll();
    releaseInstance(dataDir, instance);
}
