/** Builds the SettingsResponse DTO from configuration and live protection state (no secrets, no paths). */
import type { ProtectionState, SettingsResponse } from "@securecode/contracts";
import type { HostConfig } from "../config/hostConfig.js";
import type { RuntimeConfig } from "../config/runtimeConfig.js";

/** Approval review cap enforced by the project tools (API.md 6). */
const APPROVAL_REVIEW_MAX_BYTES = 16384;

export function buildSettings(
    hostConfig: HostConfig,
    runtimeConfig: RuntimeConfig,
    providerConfigured: boolean,
    protections: ProtectionState[],
    verifiedLocalModel = false,
): SettingsResponse {
    const gateReady = protections.some((state) => state.name === "model_request_gate" && state.ready);
    return {
        schema_version: "1",
        provider: {
            provider_id: hostConfig.providerId,
            model_id: hostConfig.modelId,
            configured: providerConfigured,
            ...(providerConfigured ? {} : { reason_code: "PROVIDER_ERROR" }),
        },
        budget: {
            context_limit_tokens: runtimeConfig.contextLimitTokens,
            max_output_tokens: runtimeConfig.maxOutputTokens,
            safety_margin_tokens: runtimeConfig.safetyMarginTokens,
            body_count_mode: providerConfigured ? (verifiedLocalModel ? "exact" : "provider_estimate") : null,
            // 4.8 verifies the gate's budget policy; a registered gate is not yet "enforced".
            final_request_gate: gateReady ? (verifiedLocalModel ? "enforced" : "not_verified") : "unavailable",
        },
        limits: { approval_review_max_bytes: APPROVAL_REVIEW_MAX_BYTES },
        protections,
    };
}
