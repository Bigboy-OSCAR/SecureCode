/** The Vite UI dev server (apps/ui), started only after the host is healthy; /api is proxied to the host. */
import { join } from "node:path";
import { launch, type LaunchedChild, type OutputSink } from "./childProcess.js";
import { nodeBin, WORK_ROOT } from "./processes.js";
import { waitReady } from "./readiness.js";

export interface UiServer {
    ui: LaunchedChild;
    uiUrl: string;
}

export interface UiOptions {
    uiPort: number;
    hostPort: number;
    signal?: AbortSignal;
    onOutput?: OutputSink;
}

export async function startUi(options: UiOptions): Promise<UiServer> {
    const [node, vite] = nodeBin(join("vite", "bin", "vite.js"));
    const env = { ...process.env, SECURECODE_HOST_PORT: String(options.hostPort) };
    // --strictPort: a port taken after the launcher's check fails instead of silently moving.
    const args = [vite, "--host", "127.0.0.1", "--port", String(options.uiPort), "--strictPort"];
    const ui = launch("ui", node, args, join(WORK_ROOT, "apps", "ui"), env, options.onOutput);
    const uiUrl = `http://127.0.0.1:${options.uiPort}`;
    try {
        await waitReady(
            {
                name: "ui",
                url: uiUrl + "/",
                ready: async (response) => response.ok && (await response.text()).includes('id="root"'),
            },
            ui,
            60000,
            options.signal,
        );
    } catch (error) {
        await ui.stop();
        throw error;
    }
    return { ui, uiUrl };
}
