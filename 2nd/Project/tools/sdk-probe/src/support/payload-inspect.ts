/**
 * Reads Anthropic Messages request bodies captured at the fetch boundary.
 */
import type { CapturedRequest } from "../fixtures/scripted-fetch.js";

interface ContentBlockSummary {
    role: string;
    type: string;
    toolUseId?: string;
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
    return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [];
}

export function listToolNames(request: CapturedRequest): string[] {
    return asRecordArray(request.body.tools).map((tool) => String(tool.name));
}

/** Flattens messages into role/type pairs to check tool_use → tool_result ordering. */
export function summarizeContentBlocks(request: CapturedRequest): ContentBlockSummary[] {
    const summaries: ContentBlockSummary[] = [];

    for (const message of asRecordArray(request.body.messages)) {
        const role = String(message.role);
        const content = message.content;
        if (typeof content === "string") {
            summaries.push({ role, type: "text" });
            continue;
        }
        for (const block of asRecordArray(content)) {
            const toolUseId = typeof block.id === "string" ? block.id : typeof block.tool_use_id === "string" ? block.tool_use_id : undefined;
            summaries.push({ role, type: String(block.type), ...(toolUseId ? { toolUseId } : {}) });
        }
    }
    return summaries;
}

/** True when every tool_result follows its tool_use in the next user message. */
export function isToolPairingPreserved(request: CapturedRequest): boolean {
    const blocks = summarizeContentBlocks(request);
    const seenToolUses = new Set<string>();

    for (const block of blocks) {
        if (block.type === "tool_use" && block.toolUseId) {
            seenToolUses.add(block.toolUseId);
        }
        if (block.type === "tool_result" && (!block.toolUseId || !seenToolUses.has(block.toolUseId))) {
            return false;
        }
    }
    const resultIds = new Set(blocks.filter((block) => block.type === "tool_result").map((block) => block.toolUseId));
    return [...seenToolUses].every((toolUseId) => resultIds.has(toolUseId));
}
