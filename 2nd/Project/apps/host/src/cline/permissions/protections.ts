/**
 * Required protections (API.md 6). Sessions and runs start only when all of
 * them are ready; otherwise the host answers PROTECTION_UNAVAILABLE and the
 * settings DTO shows which one is missing.
 */
import type { ProtectionState } from "@securecode/contracts";

export interface ProtectionInputs {
    toolResultTransformer: boolean;
    modelRequestGate: boolean;
    approvalBroker: boolean;
    toolAllowlist: boolean;
    checkpointDisabled: boolean;
}

export function describeProtections(inputs: ProtectionInputs): ProtectionState[] {
    const entry = (name: ProtectionState["name"], ready: boolean): ProtectionState =>
        ready ? { name, ready } : { name, ready, reason_code: "PROTECTION_UNAVAILABLE" };
    return [
        entry("runtime_pointer_hook", inputs.toolResultTransformer),
        entry("model_request_gate", inputs.modelRequestGate),
        entry("approval_broker", inputs.approvalBroker),
        entry("tool_allowlist", inputs.toolAllowlist),
        entry("checkpoint_disabled", inputs.checkpointDisabled),
    ];
}

export function missingProtections(states: readonly ProtectionState[]): string[] {
    return states.filter((state) => !state.ready).map((state) => state.name);
}
