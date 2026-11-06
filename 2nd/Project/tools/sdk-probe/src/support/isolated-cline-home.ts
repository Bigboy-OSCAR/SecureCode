/** Isolate SDK settings and fixture workspaces before importing the SDK in the probe process. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const probeHomeDir = mkdtempSync(join(tmpdir(), "securecode-sdk-probe-"));
process.env.CLINE_DIR = join(probeHomeDir, "settings");
process.env.CLINE_DATA_DIR = join(probeHomeDir, "data");
process.once("exit", () => {
    try {
        rmSync(probeHomeDir, { recursive: true, force: true });
    } catch {
        // Windows keeps SDK store handles open until exit (3.1 S-07); env/isolated-cline-home.ts
        // removes stale homes on the next run, so a locked folder is not a test failure.
    }
});
