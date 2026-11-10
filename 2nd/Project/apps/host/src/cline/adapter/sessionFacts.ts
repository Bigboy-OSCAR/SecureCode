/** Per-SDK-session state and the mapping of SDK facts onto the active turn's signals. */
import type { CoreFact } from "../events/coreEventMapper.js";
import type { ProjectTool } from "../tools/toolSupport.js";
import type { ActiveTurn } from "./turnContext.js";
import { describeToolFinish } from "./turnOutcome.js";

export interface SessionState {
    workspaceId: string;
    started: boolean;
    tools: Map<string, ProjectTool>;
    turn: ActiveTurn | null;
    messageIndex: number;
}

/** Forwards one SDK fact to the active turn's listener; facts outside a turn are ignored. */
export function applyCoreFact(session: SessionState, fact: CoreFact): void {
    const turn = session.turn;
    if (!turn) return;
    switch (fact.kind) {
        case "iteration_started":
            session.messageIndex += 1;
            return;
        case "text":
            turn.listener({
                kind: "output_delta",
                messageId: `${turn.runId}-m${session.messageIndex}`,
                text: fact.text,
            });
            return;
        case "tool_started":
            turn.listener({ kind: "tool_started", toolCallId: fact.toolCallId, toolName: fact.toolName });
            return;
        case "tool_finished":
            turn.listener(describeToolFinish(fact, turn.toolOutputs.get(fact.toolCallId)));
            return;
        case "status":
            return;
    }
}
