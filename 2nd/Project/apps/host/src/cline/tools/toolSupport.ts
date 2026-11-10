/** Shared pieces of the project tools: the ProjectTool shape, input field access and approval reviews. */
import type { AgentTool } from "@cline/sdk";
import type { ApprovalReview } from "@securecode/contracts";

export const REVIEW_MAX_BYTES = 16 * 1024;

export interface ProjectTool {
    tool: AgentTool;
    requiresApproval: boolean;
    review(input: unknown): ApprovalReview;
    /** Non-null reason means the host refuses without asking the user. */
    refuse(input: unknown): string | null;
}

export function field(input: unknown, name: string, required: true): string;
export function field(input: unknown, name: string, required: false): string | undefined;
export function field(input: unknown, name: string, required: boolean): string | undefined {
    const value = typeof input === "object" && input !== null ? (input as Record<string, unknown>)[name] : undefined;
    if (value === undefined && !required) return undefined;
    if (typeof value !== "string") throw new Error(`tool input field "${name}" must be a string`);
    return value;
}

/** Cuts text to a UTF-8 byte budget without splitting a character. */
export function clipUtf8(text: string, maxBytes: number): { text: string; truncated: boolean } {
    const bytes = Buffer.from(text, "utf8");
    if (bytes.length <= maxBytes) return { text, truncated: false };
    let end = maxBytes;
    while (end > 0 && ((bytes[end] ?? 0) & 0xc0) === 0x80) end -= 1;
    return { text: bytes.subarray(0, end).toString("utf8"), truncated: true };
}

export function review(
    kind: ApprovalReview["kind"],
    summary: string,
    content: string,
    paths?: string[],
): ApprovalReview {
    const clipped = clipUtf8(content, REVIEW_MAX_BYTES);
    return {
        kind,
        summary: summary.slice(0, 500),
        content: clipped.text,
        content_truncated: clipped.truncated,
        reviewable: !clipped.truncated,
        ...(paths ? { target_paths: paths } : {}),
    };
}

export const objectSchema = (properties: Record<string, unknown>, required: string[]): AgentTool["inputSchema"] => ({
    type: "object",
    properties,
    required,
    additionalProperties: false,
});
