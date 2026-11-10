/**
 * Builds the context.select request for a session (3.6) and turns a plan into the first user message.
 * Preview and run creation use the same inputs, so the same question and choices give the same
 * preview_digest. Fragments are inserted once, in the user turn that starts the run, wrapped in the
 * CONTEXT_SELECTOR.md 7.6 envelope; their ranges become history so later runs never re-insert them.
 * The final provider request is still checked by the 4.8 gate.
 */
import type { ContextPlanInput, ContextSelectResponse, ExplicitContextRef } from "@securecode/contracts";
import type { ContextServiceClient } from "../../context-client/ports.js";
import type { PromptCosts } from "../adapter/runtimePort.js";
import { RouteFailure } from "../../routes/shared/routeFailure.js";
import type { SessionContextStore } from "./sessionContext.js";

export interface ContextAssemblerOptions {
    client: ContextServiceClient;
    sessions: SessionContextStore;
    /** Registers the workspace root with the service before the first call that needs it. */
    ensureWorkspace(workspaceId: string): Promise<void>;
    /** System prompt and tool definitions the SDK sends for this workspace's sessions. */
    promptCosts(): PromptCosts;
    contextLimitTokens: number;
    maxOutputTokens: number;
    safetyMarginTokens: number;
}

type Plan = ContextSelectResponse["plan"];

/** Same envelope the service counts (display: symbol path, Source pointer, "runtime output"). */
export function renderEnvelope(candidateId: string, source: string, content: string): string {
    const safe = source.replace(/"/g, "'").replace(/\n/g, " ").slice(0, 256);
    return `<securecode-context id="${candidateId}" source="${safe}">\n${content}\n</securecode-context>`;
}

function displayOf(fragment: Plan["fragments"][number]): string {
    const provenance = fragment.provenance as { location?: { relative_path: string } };
    if (provenance.location) return provenance.location.relative_path;
    const ref = fragment.ref as { kind: string; pointer?: string };
    return ref.kind === "runtime" ? "runtime output" : (ref.pointer ?? "source");
}

export class ContextAssembler {
    constructor(private readonly options: ContextAssemblerOptions) {}

    async select(input: Omit<ContextPlanInput, "index_revision">): Promise<ContextSelectResponse> {
        const { client, sessions } = this.options;
        await this.options.ensureWorkspace(input.workspace_id);
        const index = await client.workspaces.indexStatus(input.workspace_id);
        const view = sessions.view(input.session_id);
        const costs = this.options.promptCosts();
        return client.context.select({
            schema_version: "1",
            input: { ...input, index_revision: index.index_revision ?? 1 },
            // No automatic current_task candidates: a stored output reaches the model as a pointer
            // descriptor and only the ranges the model reads (3.6 leak test: raw log heads stayed out).
            current_task_refs: [],
            history_refs: view.history,
            costs: {
                model_context_limit: this.options.contextLimitTokens,
                reserved_output_tokens: this.options.maxOutputTokens,
                safety_margin_tokens: this.options.safetyMarginTokens,
                message_overhead_tokens: 0,
                system: costs.system,
                tool_schema: costs.toolSchema,
                history: view.lastMessages,
            },
        });
    }

    /**
     * Plans the run's context, enforces the preview digest and run-creation error, and returns the
     * prompt with the fragments appended. Throws RouteFailure; nothing is recorded on failure.
     */
    async forRun(
        workspaceId: string,
        sessionId: string,
        request: { prompt: string; context_refs?: ExplicitContextRef[]; preview_digest?: string },
    ): Promise<{ prompt: string; plan: Plan }> {
        const response = await this.select({
            workspace_id: workspaceId,
            session_id: sessionId,
            prompt: request.prompt,
            context_refs: request.context_refs ?? [],
        });
        const { plan } = response;
        if (request.preview_digest && request.preview_digest !== plan.preview_digest) {
            throw new RouteFailure(
                "VALIDATION_FAILED",
                "the question or its context changed; check the preview again",
                {
                    reason: "stale_preview",
                },
            );
        }
        if (response.run_create_error) {
            const first = plan.omitted.find((row) => row.origin === "explicit");
            throw new RouteFailure(response.run_create_error, "a selected context range cannot be used", {
                reason: first?.reason ?? "explicit_omitted",
                ...(first ? { candidate_id: first.candidate_id } : {}),
            });
        }
        const blocks = plan.fragments.map((fragment) =>
            renderEnvelope(fragment.candidate_id, displayOf(fragment), fragment.content),
        );
        for (const fragment of plan.fragments) {
            const ref = (fragment.provenance as { ref: ExplicitContextRef }).ref;
            this.options.sessions.shown(sessionId, ref);
        }
        const prompt = blocks.length === 0 ? request.prompt : `${request.prompt}\n\n${blocks.join("\n\n")}`;
        return { prompt, plan };
    }
}
