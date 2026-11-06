/**
 * Per-turn state shared by the adapter's hooks, approval handler and fetch
 * gate. The fetch gate runs inside the SDK's async call chain, so the active
 * turn is also carried in AsyncLocalStorage to attribute a blocked request.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import type { ErrorCode } from "@securecode/contracts";
import type { TurnListener } from "./runtimePort.js";

export interface TurnFailure {
    code: ErrorCode;
    message: string;
}

export interface ToolOutputInfo {
    outputBytes: number;
    pointer?: string;
}

export interface ActiveTurn {
    workspaceId: string;
    sessionId: string;
    runId: string;
    listener: TurnListener;
    failure: TurnFailure | null;
    toolOutputs: Map<string, ToolOutputInfo>;
}

export const turnStorage = new AsyncLocalStorage<ActiveTurn>();

export function recordFailure(turn: ActiveTurn | undefined, failure: TurnFailure): void {
    if (turn && !turn.failure) turn.failure = failure;
}
