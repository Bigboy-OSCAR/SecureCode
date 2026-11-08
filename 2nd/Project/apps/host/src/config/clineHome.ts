/**
 * Points every SDK-owned directory at the app-only Cline home (3.1 C-02).
 * Must run before any module imports @cline/sdk, so user ~/.cline settings,
 * plugins, MCP servers and sessions never leak into SecureCode runs.
 */
import { mkdirSync } from "node:fs";
import { join } from "node:path";

export function prepareClineHome(clineHome: string, env: NodeJS.ProcessEnv = process.env): void {
    mkdirSync(join(clineHome, "data"), { recursive: true, mode: 0o700 });
    env.CLINE_DIR = clineHome;
    env.CLINE_DATA_DIR = join(clineHome, "data");
    env.CLINE_SESSION_BACKEND_MODE = "local";
}
