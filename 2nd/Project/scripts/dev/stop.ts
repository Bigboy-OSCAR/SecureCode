import { closeSync, openSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { currentInstance, devDataDir, stopRequestPath } from "./state.js";

const dataDir = devDataDir();
const state = currentInstance(dataDir);
if (!state) {
    console.log("no running dev servers recorded");
} else {
    // A stale/recycled PID must never be sent a termination signal.
    try {
        process.kill(state.launcherPid, 0);
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
        throw new Error("launcher is gone; check both servers before removing the stale dev-processes.json", {
            cause: error,
        });
    }
    try {
        closeSync(openSync(stopRequestPath(dataDir, state.instance), "wx", 0o600));
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    }
    const deadline = Date.now() + 15000;
    while (currentInstance(dataDir)?.instance === state.instance) {
        if (Date.now() >= deadline) throw new Error("launcher did not acknowledge stop; inspect the recorded instance");
        await delay(100);
    }
    console.log("dev servers stopped");
}
