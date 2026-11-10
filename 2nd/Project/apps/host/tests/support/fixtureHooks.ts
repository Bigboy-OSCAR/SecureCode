/**
 * [fixture] ToolResultTransformer and ModelRequestGate stand-ins so 3.5 can be
 * verified before 4.4/4.8 exist. They follow the port contracts (fail closed)
 * but are not the Runtime Pointer or budget policies and never ship in production.
 */
import { randomUUID } from "node:crypto";
import type {
    PointerReadRequest,
    PointerReadResult,
    PointerSearchRequest,
    PointerSearchResult,
} from "@securecode/contracts";
import type {
    ModelRequestDecision,
    ModelRequestGate,
    OutboundModelRequest,
    RuntimePointerService,
    RuntimeScope,
    RuntimeUpload,
    StoredRuntimeOutput,
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

/**
 * [fixture] In-memory Runtime store for host tests that do not start the context-service. It keeps
 * outputs per scope and answers reads with the contract shape; it is not the 4.3 store.
 */
export class FixtureRuntimeService implements RuntimePointerService {
    readonly objects = new Map<string, string>();
    mode: "normal" | "unreachable" = "normal";

    async store(scope: RuntimeScope, content: string): Promise<StoredRuntimeOutput> {
        return this.keep(scope, content);
    }

    openUpload(scope: RuntimeScope): RuntimeUpload {
        const chunks: Uint8Array[] = [];
        return {
            write: async (chunk) => {
                chunks.push(chunk);
            },
            finish: async () => this.keep(scope, Buffer.concat(chunks).toString("utf8")),
            abort: () => undefined,
        };
    }

    async read(_scope: RuntimeScope, request: Omit<PointerReadRequest, "schema_version">): Promise<PointerReadResult> {
        const content = this.objects.get(request.pointer) ?? "";
        const text = content.slice(0, request.max_bytes ?? 16384);
        return {
            schema_version: "1",
            pointer: request.pointer,
            content: text,
            provenance: { media_type: "text/plain", byte_size: Buffer.byteLength(content), revision: 1 },
            truncated: text.length < content.length,
            token_count: Buffer.byteLength(text),
            count_mode: "provider_estimate",
        };
    }

    async search(
        _scope: RuntimeScope,
        request: Omit<PointerSearchRequest, "schema_version">,
    ): Promise<PointerSearchResult> {
        const lines = (this.objects.get(request.pointer) ?? "").split("\n");
        const matches = lines
            .map((content, index) => ({ line: index + 1, content, byte_offset: 0 }))
            .filter((match) => match.content.includes(request.query));
        return {
            schema_version: "1",
            pointer: request.pointer,
            matches,
            truncated: false,
            token_count: 0,
            count_mode: "exact",
        };
    }

    async probe(): Promise<void> {
        if (this.mode === "unreachable") throw new Error("fixture store unreachable");
    }

    async clearSession(scope: RuntimeScope): Promise<number> {
        const prefix = `securecode://runtime/${scope.workspaceId}/${scope.sessionId}/`;
        const keys = [...this.objects.keys()].filter((key) => key.startsWith(prefix));
        for (const key of keys) this.objects.delete(key);
        return keys.length;
    }

    private keep(scope: RuntimeScope, content: string): StoredRuntimeOutput {
        const pointer = `securecode://runtime/${scope.workspaceId}/${scope.sessionId}/${randomUUID()}?v=1`;
        this.objects.set(pointer, content);
        return { pointer, byteSize: Buffer.byteLength(content, "utf8") };
    }
}
