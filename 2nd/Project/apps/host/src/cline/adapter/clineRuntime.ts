/**
 * AgentRuntime implemented with the installed @cline/sdk ClineCore (3.1 surface):
 * create → start (first run) / send (later runs) → subscribe → abort/stop →
 * dispose. Only this adapter, the tools and the event mapper import the SDK.
 */
import { ClineCore, type ToolApprovalRequest, type ToolApprovalResult } from "@cline/sdk";
import type { ProtectionState } from "@securecode/contracts";
import { mapCoreEvent, type CoreFact } from "../events/coreEventMapper.js";
import type { ApprovalBroker } from "../permissions/approvalBroker.js";
import { describeProtections } from "../permissions/protections.js";
import { buildToolPolicies } from "../permissions/toolPolicies.js";
import { createRuntimePointerHooks } from "../plugins/runtimePointerPlugin.js";
import type { ContextServiceClient } from "../../context-client/ports.js";
import type { SessionContextStore } from "../context/sessionContext.js";
import { ALLOWED_TOOL_NAMES, buildSessionTools, sessionToolSchema } from "../tools/sessionTools.js";
import { sessionToolOptions } from "./sessionToolOptions.js";
import type { ModelRequestGate, RuntimePointerService, ToolResultTransformer } from "./ports.js";
import { createGatedFetch } from "./requestGateFetch.js";
import type { AgentRuntime, PromptCosts, TurnListener, TurnOutcome, TurnRequest } from "./runtimePort.js";
import { buildStartInput, SYSTEM_PROMPT } from "./sessionConfig.js";
import { turnStorage, type ActiveTurn } from "./turnContext.js";
import { checkTurnReady } from "./turnGuards.js";
import { outcomeFromResult } from "./turnOutcome.js";
import { applyCoreFact, type SessionState } from "./sessionFacts.js";

export interface ClineRuntimeOptions {
    providerId: string;
    modelId: string;
    apiKey: string | null;
    baseUrl: string | null;
    maxOutputTokens: number;
    hookTimeoutMs: number;
    commandTimeoutMs: number;
    broker: ApprovalBroker;
    /** Required hooks; null keeps the protection unavailable and blocks runs (3.1 S-04). */
    transformer: ToolResultTransformer | null;
    gate: ModelRequestGate | null;
    /** 4.3 Runtime store used by the command executor and runtime tools; null blocks runs. */
    runtimePointers: RuntimePointerService | null;
    /** Executor capture limits (defaults: 4 KiB threshold, 32 MiB stored). */
    pointerThresholdBytes?: number;
    maxCapturedBytes?: number;
    /** Provider transport behind the gate; tests inject a scripted provider here. */
    providerFetch?: typeof fetch;
    /** context-service capabilities behind the Source/R0/PDF tools (3.6). */
    contextClient: ContextServiceClient;
    /** Per-session pointers, shown ranges and last request messages for the Selector. */
    sessionContext: SessionContextStore;
    /** System prompt with the exported skills appended (default: SYSTEM_PROMPT). */
    systemPrompt?: string;
}

export class ClineAgentRuntime implements AgentRuntime {
    private readonly sessions = new Map<string, SessionState>();
    /** Runs cancelled before their turn started. */
    private readonly earlyAborts = new Set<string>();
    private readonly unsubscribe: () => void;

    private constructor(
        private readonly core: ClineCore,
        private readonly options: ClineRuntimeOptions,
    ) {
        this.unsubscribe = core.subscribe((event) => {
            const mapped = mapCoreEvent(event);
            if (mapped) this.applyFact(mapped.sessionId, mapped.fact);
        });
    }

    static async create(options: ClineRuntimeOptions): Promise<ClineAgentRuntime> {
        const runtime: { instance?: ClineAgentRuntime } = {};
        const core = await ClineCore.create({
            clientName: "securecode-host",
            distinctId: "securecode-host",
            backendMode: "local",
            automation: false,
            ...(options.gate
                ? {
                      fetch: createGatedFetch({
                          gate: options.gate,
                          baseFetch: options.providerFetch ?? fetch,
                          providerId: options.providerId,
                          modelId: options.modelId,
                          maxOutputTokens: options.maxOutputTokens,
                          allowedToolNames: ALLOWED_TOOL_NAMES,
                          onOutbound: (sessionId, body) => options.sessionContext.outbound(sessionId, body),
                      }),
                  }
                : {}),
            capabilities: {
                requestToolApproval: (request) =>
                    runtime.instance
                        ? runtime.instance.requestApproval(request)
                        : Promise.resolve({ approved: false, reason: "host is starting" }),
            },
        });
        runtime.instance = new ClineAgentRuntime(core, options);
        return runtime.instance;
    }

    protections(): ProtectionState[] {
        return describeProtections({
            toolResultTransformer: this.options.transformer !== null && this.options.runtimePointers !== null,
            modelRequestGate: this.options.gate !== null,
            approvalBroker: true,
            toolAllowlist: true,
            checkpointDisabled: true,
        });
    }

    async runTurn(request: TurnRequest, listener: TurnListener): Promise<TurnOutcome> {
        const { transformer, apiKey } = this.options;
        const aborted: TurnOutcome = { finish: "aborted", text: "" };
        const refusal = await checkTurnReady(this.options, request);
        if (refusal || !transformer || !apiKey) {
            return refusal ?? { finish: "failed", text: "", reasonCode: "SDK_UNAVAILABLE", message: "not ready" };
        }
        const session = this.sessionFor(request);
        if (session.turn) {
            return { finish: "failed", text: "", reasonCode: "RUN_ALREADY_ACTIVE", message: "a run is already active" };
        }
        const turn: ActiveTurn = {
            ...request,
            listener,
            failure: null,
            toolOutputs: new Map(),
            executorCaptures: new Map(),
            cancel: new AbortController(),
        };
        session.turn = turn;
        if (this.earlyAborts.delete(request.runId)) {
            session.turn = null;
            return aborted;
        }
        try {
            const result = await turnStorage.run(turn, async () => {
                if (turn.aborted) return undefined;
                if (session.started) return this.core.send({ sessionId: request.sessionId, prompt: request.prompt });
                const projectTools = [...session.tools.values()];
                // Public SDK canonical history survives host restart and model changes. Reuse it
                // with the new connection; the final gate recounts every restored message.
                const initialMessages = await this.core.readMessages(request.sessionId);
                const started = await this.core.start(
                    buildStartInput({
                        sessionId: request.sessionId,
                        prompt: request.prompt,
                        initialMessages,
                        workspaceRoot: request.workspaceRoot,
                        providerId: this.options.providerId,
                        modelId: this.options.modelId,
                        apiKey,
                        baseUrl: this.options.baseUrl,
                        maxOutputTokens: this.options.maxOutputTokens,
                        systemPrompt: this.systemPrompt(),
                        tools: projectTools.map((entry) => entry.tool),
                        toolPolicies: buildToolPolicies(
                            projectTools.map((entry) => ({
                                name: entry.tool.name,
                                requiresApproval: entry.requiresApproval,
                            })),
                        ),
                        hooks: createRuntimePointerHooks(transformer, () => session.turn, this.options.hookTimeoutMs),
                    }),
                );
                session.started = true;
                return started.result;
            });
            if (turn.aborted || result === undefined) return aborted;
            return outcomeFromResult(result, turn.failure);
        } catch {
            return {
                finish: "failed",
                text: "",
                reasonCode: turn.failure?.code ?? "SDK_UNAVAILABLE",
                message: turn.failure?.message ?? "the SDK run failed",
            };
        } finally {
            session.turn = null;
        }
    }

    /** System prompt and tool definitions every session sends (Selector fixed costs). */
    promptCosts(): PromptCosts {
        const toolSchema = sessionToolSchema(this.options.contextClient, this.options.runtimePointers);
        return { system: this.systemPrompt(), toolSchema };
    }

    private systemPrompt(): string {
        return this.options.systemPrompt ?? SYSTEM_PROMPT;
    }

    async abortTurn(sessionId: string, reason: string, runId?: string): Promise<void> {
        // Raise the SDK abort first, then settle pending approvals: abort alone never settles
        // them (3.1 C-03), and settling first would let the SDK continue to another model call.
        const session = this.sessions.get(sessionId);
        if (session?.turn) {
            session.turn.aborted = true;
            session.turn.cancel.abort(new DOMException(reason, "AbortError"));
        }
        // A cancel that arrives before the turn exists is kept for that run (3.6 live: it was lost).
        else if (runId) this.earlyAborts.add(runId);
        const aborting = session?.started || session?.turn ? this.core.abort(sessionId, reason) : Promise.resolve();
        this.options.broker.cancelSession(sessionId);
        await aborting;
    }

    async closeSession(sessionId: string): Promise<void> {
        this.options.broker.cancelSession(sessionId);
        const session = this.sessions.get(sessionId);
        this.sessions.delete(sessionId);
        this.options.sessionContext.forget(sessionId);
        if (session?.started) await this.core.stop(sessionId);
        // Session end policy: stored outputs of this session go with it (sweep handles TTL separately).
        if (session && this.options.runtimePointers) {
            const scope = { workspaceId: session.workspaceId, sessionId };
            await this.options.runtimePointers.clearSession(scope, AbortSignal.timeout(5000)).catch(() => 0);
        }
    }

    async dispose(): Promise<void> {
        for (const sessionId of this.sessions.keys()) this.options.broker.cancelSession(sessionId);
        this.unsubscribe();
        await this.core.dispose("securecode host shutdown");
    }

    private sessionFor(request: TurnRequest): SessionState {
        let session = this.sessions.get(request.sessionId);
        if (!session) {
            const service = this.options.runtimePointers;
            if (!service) throw new Error("runtime pointer store is not configured");
            const holder: { session?: SessionState } = {};
            const tools = buildSessionTools(
                sessionToolOptions(
                    this.options,
                    request,
                    service,
                    (toolCallId, capture) => holder.session?.turn?.executorCaptures.set(toolCallId, capture),
                    () => holder.session?.turn?.runId,
                ),
            );
            session = {
                workspaceId: request.workspaceId,
                started: false,
                tools: new Map(tools.map((tool) => [tool.tool.name, tool])),
                turn: null,
                messageIndex: 0,
            };
            holder.session = session;
            this.sessions.set(request.sessionId, session);
        }
        return session;
    }

    private async requestApproval(request: ToolApprovalRequest): Promise<ToolApprovalResult> {
        const session = this.sessions.get(request.sessionId);
        const turn = session?.turn;
        const tool = session?.tools.get(request.toolName);
        if (!session || !turn || !tool) return { approved: false, reason: "tool is not allowed in this run" };
        if (turn.aborted) return { approved: false, reason: "the run was cancelled" };
        let refusal: string | null;
        let review;
        try {
            refusal = tool.refuse(request.input);
            review = tool.review(request.input);
        } catch {
            refusal = "tool input is invalid";
        }
        if (refusal || !review) {
            turn.listener({
                kind: "tool_finished",
                toolCallId: request.toolCallId,
                toolName: request.toolName,
                isError: true,
                summary: `refused: ${refusal ?? "tool input is invalid"}`,
            });
            return { approved: false, reason: refusal ?? "tool input is invalid" };
        }
        return this.options.broker.request({
            sessionId: request.sessionId,
            runId: turn.runId,
            toolCallId: request.toolCallId,
            toolName: request.toolName,
            input: request.input,
            review,
        });
    }

    private applyFact(sessionId: string, fact: CoreFact): void {
        const session = this.sessions.get(sessionId);
        if (session) applyCoreFact(session, fact);
    }
}
