/** [fixture] Scriptable AgentRuntime for route-level tests that do not need the SDK. */
import type { ProtectionState } from "@securecode/contracts";
import type { AgentRuntime, TurnListener, TurnOutcome, TurnRequest } from "../../src/cline/adapter/runtimePort.js";
import { describeProtections } from "../../src/cline/permissions/protections.js";

export class FakeRuntime implements AgentRuntime {
    ready = true;
    readonly turns: TurnRequest[] = [];
    readonly aborted: string[] = [];
    private release: ((outcome: TurnOutcome) => void) | null = null;
    listener: TurnListener | null = null;

    runTurn(request: TurnRequest, listener: TurnListener): Promise<TurnOutcome> {
        this.turns.push(request);
        this.listener = listener;
        return new Promise((resolve) => {
            this.release = resolve;
        });
    }

    finish(outcome: TurnOutcome): void {
        this.release?.(outcome);
        this.release = null;
    }

    async abortTurn(sessionId: string): Promise<void> {
        this.aborted.push(sessionId);
        this.finish({ finish: "aborted", text: "" });
    }

    async closeSession(): Promise<void> {}

    promptCosts(): { system: string; toolSchema: string } {
        return { system: "fixture system prompt", toolSchema: "[]" };
    }

    async dispose(): Promise<void> {
        this.finish({ finish: "aborted", text: "" });
    }

    protections(): ProtectionState[] {
        return describeProtections({
            toolResultTransformer: this.ready,
            modelRequestGate: this.ready,
            approvalBroker: true,
            toolAllowlist: true,
            checkpointDisabled: true,
        });
    }
}
