/** `npm run stop`: stops the servers recorded by `npm run dev` in another terminal. */
import { existsSync, readFileSync, rmSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import { WORK_ROOT } from "../lib/processes.js";
import { devStatePath, type DevState } from "./state.js";

const envFile = join(WORK_ROOT, ".env");
if (existsSync(envFile)) {
    process.loadEnvFile(envFile);
}
const dataDirSetting = process.env.SECURECODE_DATA_DIR?.trim() || ".securecode";
const dataDir = isAbsolute(dataDirSetting) ? dataDirSetting : resolve(WORK_ROOT, dataDirSetting);
const statePath = devStatePath(dataDir);

if (!existsSync(statePath)) {
    console.log("no running dev servers recorded");
} else {
    const state = JSON.parse(readFileSync(statePath, "utf8")) as DevState;
    for (const [label, pid] of [
        ["host", state.host_pid],
        ["context-service", state.service_pid],
    ] as const) {
        if (pid === undefined) {
            continue;
        }
        try {
            process.kill(pid, "SIGTERM");
            console.log(`stopped ${label} (pid ${pid})`);
        } catch {
            console.log(`${label} (pid ${pid}) was not running`);
        }
    }
    rmSync(statePath, { force: true });
}
