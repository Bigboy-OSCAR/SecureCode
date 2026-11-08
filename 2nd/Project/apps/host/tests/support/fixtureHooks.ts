/**
 * [fixture] ToolResultTransformer and ModelRequestGate stand-ins so 3.5 can be
 * verified before 4.4/4.8 exist. They follow the port contracts (fail closed)
 * but are not the Runtime Pointer or budget policies and never ship in production.
 */
import { randomUUID } from "node:crypto";
import type {
    ModelRequestDecision,
    ModelRequestGate,
    OutboundModelRequest,
    ToolResultInput,
    ToolResultOutput,
    ToolResultTransformer,
} from "../../src/cline/adapter/ports.js";

export class FixtureTransformer implements ToolResultTransformer {
    readonly inputs: ToolResultInput[] = [];
    mode: "normal" | "fail" | "hang" = "normal";

    constructor(readonly thresholdBytes = 4096) {}

    async transform(input: ToolResultInput, signal: AbortSignal): Promise<ToolResultOutput> {
        this.inputs.push(input);
        if (this.mode === "fail") throw new Error("fixture store failure");
        if (this.mode === "hang") {
            await new Promise((_resolve, reject) =>
                signal.addEventListener("abort", () => reject(new Error("aborted"))),
            );
        }
        if (input.outputBytes < this.thresholdBytes) return { kind: "inline", text: input.output };
        const pointer = `securecode://runtime/${input.workspaceId}/${input.sessionId}/${randomUUID()}?v=1`;
        return {
            kind: "pointer",
            pointer,
            byteSize: input.outputBytes,
            text: JSON.stringify({ kind: "runtime", pointer, byte_size: input.outputBytes }),
        };
    }
}

export class FixtureGate implements ModelRequestGate {
    readonly requests: OutboundModelRequest[] = [];
    mode: "allow" | "block" | "throw" = "allow";

    async check(request: OutboundModelRequest): Promise<ModelRequestDecision> {
        this.requests.push(request);
        if (this.mode === "throw") throw new Error("fixture gate failure");
        if (this.mode === "block") return { allow: false, code: "BUDGET_EXCEEDED", message: "fixture budget exceeded" };
        // Bytes are not tokens; the fixture only reports a number in the decision shape.
        return { allow: true, countedTokens: Buffer.byteLength(request.body), countMode: "provider_estimate" };
    }
}
