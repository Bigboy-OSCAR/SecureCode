/**
 * `npm run test:e2e`: browser end-to-end flows (UI-01..UI-34). The UI does not
 * exist yet, so this reports PENDING (exit 3) instead of passing.
 */
import { existsSync } from "node:fs";
import { join } from "node:path";
import { pendingResults } from "../lib/pendingSuites.js";
import { WORK_ROOT } from "../lib/processes.js";
import { runAndExit, type StepResult } from "../lib/report.js";

function uiPresence(): StepResult[] {
    const exists = existsSync(join(WORK_ROOT, "apps", "ui", "package.json"));
    return exists
        ? [{ name: "ui package", status: "FAIL", detail: "apps/ui exists but no e2e runner is registered here" }]
        : [];
}

await runAndExit("test:e2e", [() => Promise.resolve(uiPresence()), () => Promise.resolve(pendingResults("e2e"))]);
