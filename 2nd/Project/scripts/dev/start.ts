/**
 * `npm run dev`: context-service -> host -> UI on 127.0.0.1 in readiness order. Ctrl+C, SIGTERM or
 * `npm run stop` stop every child; a child that exits unexpectedly stops the rest and fails the launcher.
 */
import { existsSync } from "node:fs";
import { once } from "node:events";
import { startStack, type Stack } from "../lib/devStack.js";
import { claimInstance, devDataDir, releaseInstance, stopRequestPath } from "./state.js";

const readPort = (name: string, fallback: number): number => Number(process.env[name]?.trim() || fallback);

const dataDir = devDataDir();
const instance = claimInstance(dataDir);
const controller = new AbortController();
const shutdown = (): void => controller.abort();
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
process.once("SIGHUP", shutdown);
const checkStop = setInterval(() => {
    if (existsSync(stopRequestPath(dataDir, instance))) shutdown();
}, 150);

let stack: Stack | undefined;
try {
    stack = await startStack({
        hostPort: readPort("SECURECODE_HOST_PORT", 8787),
        servicePort: readPort("SECURECODE_CONTEXT_SERVICE_PORT", 8788),
        uiPort: readPort("SECURECODE_UI_DEV_PORT", 5173),
        dataDir,
        signal: controller.signal,
        onOutput: (source, chunk) => process.stdout.write(`[${source}] ${chunk}`),
    });
    console.log(
        [
            `SecureCode UI: ${stack.ui.uiUrl}  (host ${stack.services.hostUrl}/api/v1/health)`,
            `Launch code (single use, 10 min): ${stack.services.bootstrapCode}`,
            "Ctrl+C or npm run stop to stop.",
        ].join("\n"),
    );
    if (!controller.signal.aborted) {
        const children = stack.children();
        if (children.some((child) => child.exitCode !== null || child.signalCode !== null)) {
            throw new Error("a server exited during startup");
        }
        await Promise.race([
            once(controller.signal, "abort"),
            ...children.map(async (child) => {
                await once(child, "exit");
                // Children exiting during our own shutdown are expected, not a failure.
                if (!controller.signal.aborted)
                    throw new Error("a server exited unexpectedly; the others were stopped");
            }),
        ]);
    }
} catch (error) {
    if (!controller.signal.aborted) {
        console.error(`dev: ${error instanceof Error ? error.message : String(error)}`);
        process.exitCode = 1;
        controller.abort();
    }
} finally {
    clearInterval(checkStop);
    await stack?.stopAll();
    releaseInstance(dataDir, instance);
}
