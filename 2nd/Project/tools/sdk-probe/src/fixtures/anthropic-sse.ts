/**
 * Builds Anthropic Messages API streaming bodies for the scripted provider.
 * The SDK's real `anthropic` provider adapter parses these bytes, so the probe
 * exercises the installed provider path instead of a fake model object.
 */

export interface ScriptedToolUse {
    toolUseId: string;
    toolName: string;
    input: Record<string, unknown>;
}

export interface ScriptedTurn {
    text?: string;
    toolUses?: ScriptedToolUse[];
    /** Wait until the request is aborted before answering (abort scenarios). */
    holdUntilAborted?: boolean;
}

interface SseEvent {
    event: string;
    data: Record<string, unknown>;
}

function buildMessageStart(messageId: string, modelId: string): SseEvent {
    return {
        event: "message_start",
        data: {
            type: "message_start",
            message: {
                id: messageId,
                type: "message",
                role: "assistant",
                model: modelId,
                content: [],
                stop_reason: null,
                stop_sequence: null,
                usage: { input_tokens: 1, output_tokens: 1 },
            },
        },
    };
}

function buildTextBlock(index: number, text: string): SseEvent[] {
    return [
        {
            event: "content_block_start",
            data: { type: "content_block_start", index, content_block: { type: "text", text: "" } },
        },
        {
            event: "content_block_delta",
            data: { type: "content_block_delta", index, delta: { type: "text_delta", text } },
        },
        { event: "content_block_stop", data: { type: "content_block_stop", index } },
    ];
}

function buildToolUseBlock(index: number, toolUse: ScriptedToolUse): SseEvent[] {
    const contentBlock = { type: "tool_use", id: toolUse.toolUseId, name: toolUse.toolName, input: {} };
    const inputDelta = { type: "input_json_delta", partial_json: JSON.stringify(toolUse.input) };

    return [
        { event: "content_block_start", data: { type: "content_block_start", index, content_block: contentBlock } },
        { event: "content_block_delta", data: { type: "content_block_delta", index, delta: inputDelta } },
        { event: "content_block_stop", data: { type: "content_block_stop", index } },
    ];
}

export function buildTurnSseBody(turn: ScriptedTurn, messageId: string, modelId: string): string {
    const events: SseEvent[] = [buildMessageStart(messageId, modelId)];
    let blockIndex = 0;

    if (turn.text !== undefined) {
        events.push(...buildTextBlock(blockIndex, turn.text));
        blockIndex += 1;
    }
    for (const toolUse of turn.toolUses ?? []) {
        events.push(...buildToolUseBlock(blockIndex, toolUse));
        blockIndex += 1;
    }

    const stopReason = (turn.toolUses?.length ?? 0) > 0 ? "tool_use" : "end_turn";
    events.push({
        event: "message_delta",
        data: {
            type: "message_delta",
            delta: { stop_reason: stopReason, stop_sequence: null },
            usage: { output_tokens: 1 },
        },
    });
    events.push({ event: "message_stop", data: { type: "message_stop" } });

    return events.map((sseEvent) => `event: ${sseEvent.event}\ndata: ${JSON.stringify(sseEvent.data)}\n\n`).join("");
}
