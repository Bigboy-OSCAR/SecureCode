/**
 * `npm run dev`: loads .env, prepares the data directory, starts the
 * context-service and the host on 127.0.0.1 with a per-start internal token,
 * and stops both on Ctrl+C. Pending pieces (UI, bootstrap) are printed, not faked.
 */
import { existsSync, rmSync, writeFileSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import { PENDING_SUITES } from "../lib/pendingSuites.js";
import { WORK_ROOT } from "../lib/processes.js";
import { startServices } from "../lib/services.js";
import { devStatePath } from "./state.js";

const envFile = join(WORK_ROOT, ".env");
if (existsSync(envFile)) {
    process.loadEnvFile(envFile);
}

const dataDirSetting = process.env.SECURECODE_DATA_DIR?.trim() || ".securecode";
const dataDir = isAbsolute(dataDirSetting) ? dataDirSetting : resolve(WORK_ROOT, dataDirSetting);
const hostPort = Number(process.env.SECURECODE_HOST_PORT ?? "8787");
const servicePort = Number(process.env.SECURECODE_CONTEXT_SERVICE_PORT ?? "8788");

const services = await startServices({
    hostPort,
    servicePort,
    dataDir,
    onOutput: (source, chunk) => process.stdout.write(`[${source}] ${chunk}`),
});

const statePath = devStatePath(dataDir);
writeFileSync(
    statePath,
    `${JSON.stringify({ host_pid: services.host.pid, service_pid: services.service.pid, host_port: hostPort, service_port: servicePort, started_at: new Date().toISOString() }, null, 4)}\n`,
);

console.log(`\nSecureCode dev: host ${services.hostUrl}/api/v1/health, context-service on 127.0.0.1:${servicePort}`);
for (const suite of PENDING_SUITES.filter((item) => item.command === "dev")) {
    console.log(`PENDING ${suite.name} [owner ${suite.ownerTask}]: ${suite.detail}`);
}
console.log("PENDING browser bootstrap code [owner 3.5]: POST /api/v1/auth/bootstrap answers 501 until 3.5");
console.log("Press Ctrl+C (or run `npm run stop`) to stop both servers.");

const shutdown = async (): Promise<void> => {
    await services.stopAll();
    rmSync(statePath, { force: true });
    process.exit(0);
};
process.once("SIGINT", () => void shutdown());
process.once("SIGTERM", () => void shutdown());
services.host.once("exit", () => void shutdown());
services.service.once("exit", () => void shutdown());
