/**
 * Scenario: final-request gate at the `ClineCoreOptions.fetch` boundary, after
 * the provider adapter has serialized system/tools/messages. Without a pointer
 * hook the second request carries sentinel output (SDK-truncated); the gate must
 * block it before it leaves the process and the run must fail visibly.
 * The probe gate counts UTF-8 bytes only — it is NOT a token count; 4.8 swaps
 * in the provider counter (see SDK_COMPATIBILITY.md, tokenizer decision).
 */
import { createSentinelTool, SENTINEL_MARKER, SENTINEL_TOOL_NAME } from "../fixtures/probe-tools.js";
import type { CapturedRequest, OutboundGateDecision } from "../fixtures/scripted-fetch.js";
import { errorMessage, withProbeRun } from "../probe/probe-run.js";
import { buildProbeStartInput } from "../probe/session-config.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

// Below the ~8.9 KB request #2 that remains after the SDK's own 8,000-char tool-result truncation.
const OUTBOUND_BYTE_CAP = 4 * 1024;

/** Fields a provider token-count request would need, derived from the final body. */
function buildCountRequestFields(request: CapturedRequest): string[] {
    return ["model", "system", "tools", "messages", "tool_choice"].filter((field) => field in request.body);
}

function gateByBytes(request: CapturedRequest): OutboundGateDecision {
    if (request.bodyBytes > OUTBOUND_BYTE_CAP) {
        return {
            allowed: false,
            reason: `BUDGET_EXCEEDED: outbound ${request.bodyBytes} bytes > cap ${OUTBOUND_BYTE_CAP}`,
        };
    }
    return { allowed: true };
}

export async function runOutboundGateScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("outbound-gate");
    const turns = [
        { toolUses: [{ toolUseId: "toolu_gate_1", toolName: SENTINEL_TOOL_NAME, input: { label: "big" } }] },
        { text: "must never be reached" },
    ];

    try {
        await withProbeRun(
            { name: "outbound-gate", turns, outboundGate: gateByBytes },
            async ({ core, scriptedFetch, workspaceDir, coreEvents }) => {
                const outcome = await core
                    .start(
                        buildProbeStartInput({
                            cwd: workspaceDir,
                            prompt: "make log",
                            extraTools: [createSentinelTool()],
                        }),
                    )
                    .then(
                        (result) => `resolved:${result.result?.finishReason}`,
                        (error: unknown) => `rejected:${errorMessage(error)}`,
                    );
                const blocked = scriptedFetch.blockedRequests;
                const delivered = scriptedFetch.capturedRequests;
                const errorSurfaced = coreEvents.some((event) => JSON.stringify(event).includes("BUDGET_EXCEEDED"));

                recorder.check(
                    "first request delivered under cap",
                    delivered.length === 1 && (delivered[0]?.bodyBytes ?? 0) <= OUTBOUND_BYTE_CAP,
                    `delivered=${delivered.length}`,
                );
                recorder.check(
                    "oversized final payload blocked at fetch",
                    blocked.length >= 1 && (blocked[0]?.bodyText.includes(SENTINEL_MARKER) ?? false),
                    `blocked_attempts=${blocked.length} bytes=${blocked[0]?.bodyBytes}`,
                );
                recorder.check(
                    "blocked payload never delivered",
                    !delivered.some((request) => request.bodyText.includes(SENTINEL_MARKER)),
                    "scripted server never saw sentinel",
                );
                recorder.check(
                    "run fails instead of completing",
                    outcome === "resolved:error" || outcome.startsWith("rejected:"),
                    outcome.slice(0, 160),
                );
                recorder.observe("blocked_attempts_including_sdk_retries", blocked.length);
                recorder.observe("budget_error_visible_in_core_events", errorSurfaced);
                recorder.observe(
                    "count_request_fields_available",
                    delivered[0] ? buildCountRequestFields(delivered[0]) : [],
                );
            },
        );
    } catch (error) {
        recorder.fail("scenario threw", error);
    }
    return recorder.finish();
}
