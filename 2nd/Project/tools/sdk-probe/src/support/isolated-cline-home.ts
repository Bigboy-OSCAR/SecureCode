/** Isolate SDK settings and fixture workspaces before importing the SDK in the probe process. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const probeHomeDir = mkdtempSync(join(tmpdir(), "securecode-sdk-probe-"));
process.env.CLINE_DIR = join(probeHomeDir, "settings");
process.env.CLINE_DATA_DIR = join(probeHomeDir, "data");
process.once("exit", () => rmSync(probeHomeDir, { recursive: true, force: true }));
