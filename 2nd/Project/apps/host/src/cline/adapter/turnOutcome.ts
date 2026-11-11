/**
 * Turns SDK results into run outcomes. start/send usually resolve even on
 * failure, so the run status comes from finishReason (3.1 C-05), refined by
 * the failure a hook or the fetch gate recorded for the same turn.
 */
import type { AgentResult } from "@cline/sdk";
import type { CoreFact } from "../events/coreEventMapper.js";
import type { TurnOutcome, TurnSignal } from "./runtimePort.js";
import type { ToolOutputInfo, TurnFailure } from "./turnContext.js";

export function outcomeFromResult(result: AgentResult | undefined, failure: TurnFailure | null): TurnOutcome {
    if (!result) {
        return {
            finish: "failed",
            text: "",
            reasonCode: failure?.code ?? "SDK_UNAVAILABLE",
            message: failure?.message ?? "the SDK returned no result",
        };
    }
    switch (result.finishReason) {
        case "completed":
            return failure
                ? { finish: "failed", text: result.text, reasonCode: failure.code, message: failure.message }
                : { finish: "completed", text: result.text };
        case "aborted":
            // A host hook's stop is also reported as aborted by the SDK. Preserve its reason;
            // explicit user cancellation is handled before this conversion in runTurn().
            return failure
                ? { finish: "failed", text: result.text, reasonCode: failure.code, message: failure.message }
                : { finish: "aborted", text: result.text };
        case "error":
        case "max_iterations":
        case "mistake_limit":
            return {
                finish: "failed",
                // On "error" the SDK puts the provider error text here; it is not an answer and may echo
                // provider internals (1.6 E2E). Text the model streamed before the error is already recorded.
                text: result.finishReason === "error" ? "" : result.text,
                reasonCode: failure?.code ?? "PROVIDER_ERROR",
                message: failure?.message ?? `the model run stopped (${result.finishReason})`,
            };
    }
}

export function describeToolFinish(
    fact: Extract<CoreFact, { kind: "tool_finished" }>,
    info: ToolOutputInfo | undefined,
): TurnSignal {
    const size = info ? ` (${info.outputBytes} bytes${info.pointer ? ", stored as a runtime pointer" : ""})` : "";
    return {
        kind: "tool_finished",
        toolCallId: fact.toolCallId,
        toolName: fact.toolName,
        isError: fact.failed,
        summary: `${fact.toolName} ${fact.failed ? "failed" : "completed"}${size}`,
        ...(info ? { outputBytes: info.outputBytes } : {}),
        ...(info?.pointer ? { outputPointer: info.pointer } : {}),
    };
}
