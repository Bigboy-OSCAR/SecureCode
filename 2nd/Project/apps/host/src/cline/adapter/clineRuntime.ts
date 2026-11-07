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
import { createWorkspaceTools, type ProjectTool } from "../tools/workspaceTools.js";
import type { ModelRequestGate, ToolResultTransformer } from "./ports.js";
import { createGatedFetch } from "./requestGateFetch.js";
import type { AgentRuntime, TurnListener, TurnOutcome, TurnRequest } from "./runtimePort.js";
import { buildStartInput } from "./sessionConfig.js";
import { createAfterToolHook } from "./toolResultHook.js";
import { turnStorage, type ActiveTurn } from "./turnContext.js";
import { describeToolFinish, outcomeFromResult } from "./turnOutcome.js";

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
    /** Provider transport behind the gate; tests inject a scripted provider here. */
    providerFetch?: typeof fetch;
}

interface SessionState {
    started: boolean;
    tools: Map<string, ProjectTool>;
    turn: ActiveTurn | null;
    messageIndex: number;
}

export class ClineAgentRuntime implements AgentRuntime {
    private readonly sessions = new Map<string, SessionState>();
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
        const allowedTools = new Set(["read_file", "list_files", "write_file", "run_command", "runtime_read", "runtime_search"]);
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
                          allowedToolNames: allowedTools,
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
            toolResultTransformer: this.options.transformer !== null,
            modelRequestGate: this.options.gate !== null,
            approvalBroker: true,
            toolAllowlist: true,
            checkpointDisabled: true,
        });
    }

    async runTurn(request: TurnRequest, listener: TurnListener): Promise<TurnOutcome> {
        const { transformer, apiKey } = this.options;
        if (!transformer || !this.options.gate) {
            return {
                finish: "failed",
                text: "",
                reasonCode: "PROTECTION_UNAVAILABLE",
                message: "required hooks are not registered",
            };
        }
        if (!apiKey) {
            return {
                finish: "failed",
                text: "",
                reasonCode: "PROVIDER_ERROR",
                message: "the model provider is not configured",
            };
        }
        const session = this.sessionFor(request);
        if (session.turn) {
            return { finish: "failed", text: "", reasonCode: "RUN_ALREADY_ACTIVE", message: "a run is already active" };
        }
        const turn: ActiveTurn = { ...request, listener, failure: null, toolOutputs: new Map() };
        session.turn = turn;
        try {
            const result = await turnStorage.run(turn, async () => {
                if (session.started) return this.core.send({ sessionId: request.sessionId, prompt: request.prompt });
                const projectTools = [...session.tools.values()];
                const started = await this.core.start(
                    buildStartInput({
                        sessionId: request.sessionId,
                        prompt: request.prompt,
                        workspaceRoot: request.workspaceRoot,
                        providerId: this.options.providerId,
                        modelId: this.options.modelId,
                        apiKey,
                        baseUrl: this.options.baseUrl,
                        maxOutputTokens: this.options.maxOutputTokens,
                        tools: projectTools.map((entry) => entry.tool),
                        toolPolicies: buildToolPolicies(
                            projectTools.map((entry) => ({
                                name: entry.tool.name,
                                requiresApproval: entry.requiresApproval,
                            })),
                        ),
                        hooks: {
                            afterTool: createAfterToolHook(transformer, () => session.turn, this.options.hookTimeoutMs),
                        },
                    }),
                );
                session.started = true;
                return started.result;
            });
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

    async abortTurn(sessionId: string, reason: string): Promise<void> {
        // Raise the SDK abort first, then settle pending approvals: abort alone never settles
        // them (3.1 C-03), and settling first would let the SDK continue to another model call.
        const session = this.sessions.get(sessionId);
        const aborting = session?.started || session?.turn ? this.core.abort(sessionId, reason) : Promise.resolve();
        this.options.broker.cancelSession(sessionId);
        await aborting;
    }

    async closeSession(sessionId: string): Promise<void> {
        this.options.broker.cancelSession(sessionId);
        const session = this.sessions.get(sessionId);
        this.sessions.delete(sessionId);
        if (session?.started) await this.core.stop(sessionId);
    }

    async dispose(): Promise<void> {
        for (const sessionId of this.sessions.keys()) this.options.broker.cancelSession(sessionId);
        this.unsubscribe();
        await this.core.dispose("securecode host shutdown");
    }

    private sessionFor(request: TurnRequest): SessionState {
        let session = this.sessions.get(request.sessionId);
        if (!session) {
            const tools = createWorkspaceTools({
                root: request.workspaceRoot,
                commandTimeoutMs: this.options.commandTimeoutMs,
                pointer: {
                    baseUrl: this.options.baseUrl ?? undefined,
                    internalToken: process.env.SECURECODE_INTERNAL_TOKEN,
                    workspaceId: request.workspaceId,
                    sessionId: request.sessionId,
                },
            });
            session = {
                started: false,
                tools: new Map(tools.map((tool) => [tool.tool.name, tool])),
                turn: null,
                messageIndex: 0,
            };
            this.sessions.set(request.sessionId, session);
        }
        return session;
    }

    private async requestApproval(request: ToolApprovalRequest): Promise<ToolApprovalResult> {
        const session = this.sessions.get(request.sessionId);
        const turn = session?.turn;
        const tool = session?.tools.get(request.toolName);
        if (!session || !turn || !tool) return { approved: false, reason: "tool is not allowed in this run" };
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
        const turn = session?.turn;
        if (!session || !turn) return;
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
}
