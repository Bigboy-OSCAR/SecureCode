/**
 * `npm run dev` stack: context-service -> host -> UI, each started only after the previous one is ready.
 * All three ports are checked before anything starts; a later failure stops every child already started.
 */
import type { OutputSink } from "./childProcess.js";
import { checkPort } from "./ports.js";
import { startServices, type Services } from "./services.js";
import { startUi, type UiOptions, type UiServer } from "./uiServer.js";

export interface StackOptions {
    hostPort: number;
    servicePort: number;
    uiPort: number;
    dataDir: string;
    signal?: AbortSignal;
    onOutput?: OutputSink;
    /** Injected in tests to exercise the partial-start cleanup. */
    uiStarter?: (options: UiOptions) => Promise<UiServer>;
}

export interface Stack {
    services: Services;
    ui: UiServer;
    /** Every child process of the stack, for exit monitoring. */
    children(): Services["host"][];
    stopAll(): Promise<void>;
}

export async function startStack(options: StackOptions): Promise<Stack> {
    const { hostPort, servicePort, uiPort } = options;
    if (new Set([hostPort, servicePort, uiPort]).size !== 3) {
        throw new Error("SECURECODE_HOST_PORT, SECURECODE_CONTEXT_SERVICE_PORT and SECURECODE_UI_DEV_PORT must differ");
    }
    await checkPort(uiPort, "SECURECODE_UI_DEV_PORT");
    const services = await startServices(options);
    let ui: UiServer;
    try {
        ui = await (options.uiStarter ?? startUi)({
            uiPort,
            hostPort,
            signal: options.signal,
            onOutput: options.onOutput,
        });
    } catch (error) {
        await services.stopAll();
        throw error;
    }
    return {
        services,
        ui,
        children: () => [ui.ui.child, services.host, services.service],
        stopAll: async () => {
            await ui.ui.stop();
            await services.stopAll();
        },
    };
}
