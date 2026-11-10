/**
 * SDK-independent port between the run service and the Cline adapter. Routes
 * and the run state machine depend only on these shapes; the adapter maps
 * @cline/sdk calls and CoreSessionEvent values onto them (3.5 condition 2).
 */
import type { ErrorCode, ProtectionState } from "@securecode/contracts";

export interface TurnRequest {
    workspaceId: string;
    sessionId: string;
    runId: string;
    /** Absolute workspace root; never sent to the browser. */
    workspaceRoot: string;
    prompt: string;
}

/** Facts the adapter extracts from SDK events. Raw tool output never appears here. */
export type TurnSignal =
    | { kind: "output_delta"; messageId: string; text: string }
    | { kind: "tool_started"; toolCallId: string; toolName: string }
    | {
          kind: "tool_finished";
          toolCallId: string;
          toolName: string;
          isError: boolean;
          summary: string;
          outputBytes?: number;
          outputPointer?: string;
      }
    | { kind: "pointer_created"; toolCallId: string; pointer: string; byteSize: number };

export type TurnListener = (signal: TurnSignal) => void;

export interface TurnOutcome {
    finish: "completed" | "aborted" | "failed";
    text: string;
    reasonCode?: ErrorCode;
    message?: string;
}

/** Fixed request parts every session sends: system prompt and tool definitions (Selector costs). */
export interface PromptCosts {
    system: string;
    toolSchema: string;
}

export interface AgentRuntime {
    promptCosts(): PromptCosts;
    /** Runs one user turn; resolves (never rejects) with the outcome derived from finishReason. */
    runTurn(request: TurnRequest, listener: TurnListener): Promise<TurnOutcome>;
    /** Aborts the current turn only; the SDK session stays usable. */
    abortTurn(sessionId: string, reason: string, runId?: string): Promise<void>;
    closeSession(sessionId: string): Promise<void>;
    dispose(): Promise<void>;
    protections(): ProtectionState[];
}
