/**
 * Reduces installed-SDK CoreSessionEvent values to the few facts the host
 * uses (EVENTS.md 7). The agent_event payload is unpacked here and nowhere
 * else; chunk, session_snapshot, ended, hook and team events stay internal,
 * and tool output text is never copied into a fact.
 */
import type { CoreSessionEvent } from "@cline/sdk";

export type CoreFact =
    | { kind: "iteration_started" }
    | { kind: "text"; text: string }
    | { kind: "tool_started"; toolCallId: string; toolName: string }
    | { kind: "tool_finished"; toolCallId: string; toolName: string; failed: boolean }
    | { kind: "status"; status: string };

export interface MappedCoreEvent {
    sessionId: string;
    fact: CoreFact;
}

export function mapCoreEvent(event: CoreSessionEvent): MappedCoreEvent | null {
    if (event.type === "status") {
        return { sessionId: event.payload.sessionId, fact: { kind: "status", status: event.payload.status } };
    }
    if (event.type !== "agent_event") return null;
    const { sessionId, event: agentEvent, teamRole } = event.payload;
    // Team agents are disabled; a teammate event would mean the safety config was bypassed.
    if (teamRole === "teammate") return null;
    switch (agentEvent.type) {
        case "iteration_start":
            return { sessionId, fact: { kind: "iteration_started" } };
        case "content_start":
            if (agentEvent.contentType === "text" && agentEvent.text) {
                return { sessionId, fact: { kind: "text", text: agentEvent.text } };
            }
            if (agentEvent.contentType === "tool" && agentEvent.toolCallId) {
                return {
                    sessionId,
                    fact: {
                        kind: "tool_started",
                        toolCallId: agentEvent.toolCallId,
                        toolName: agentEvent.toolName ?? "",
                    },
                };
            }
            return null;
        case "content_end":
            if (agentEvent.contentType === "tool" && agentEvent.toolCallId) {
                return {
                    sessionId,
                    fact: {
                        kind: "tool_finished",
                        toolCallId: agentEvent.toolCallId,
                        toolName: agentEvent.toolName ?? "",
                        failed: Boolean(agentEvent.error),
                    },
                };
            }
            return null;
        case "content_update":
        case "iteration_end":
        case "notice":
        case "usage":
        case "done":
        case "error":
            return null;
    }
}
