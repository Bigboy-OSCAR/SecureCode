/** Session tool options from the runtime options and one turn request (keeps clineRuntime.ts small). */
import type { SessionToolOptions } from "../tools/sessionTools.js";
import type { ClineRuntimeOptions } from "./clineRuntime.js";
import type { ExecutorCapture, RuntimePointerService } from "./ports.js";
import type { TurnRequest } from "./runtimePort.js";

export function sessionToolOptions(
    options: ClineRuntimeOptions,
    request: TurnRequest,
    service: RuntimePointerService,
    recordCapture: (toolCallId: string, capture: ExecutorCapture) => void,
): SessionToolOptions {
    return {
        root: request.workspaceRoot,
        workspaceId: request.workspaceId,
        commandTimeoutMs: options.commandTimeoutMs,
        serviceTimeoutMs: Math.max(options.hookTimeoutMs, 15000),
        client: options.contextClient,
        recordShown: (ref) => options.sessionContext.shown(request.sessionId, ref),
        runtime: {
            service,
            scope: { workspaceId: request.workspaceId, sessionId: request.sessionId },
            thresholdBytes: options.pointerThresholdBytes ?? 4096,
            maxStoredBytes: options.maxCapturedBytes ?? 32 * 1024 * 1024,
            timeoutMs: options.hookTimeoutMs,
            recordCapture,
        },
    };
}
