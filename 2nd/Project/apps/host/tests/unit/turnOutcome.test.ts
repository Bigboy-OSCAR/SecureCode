/**
 * 1.6 E2E regression: when the provider fails, the SDK's error text must not become the answer
 * (it can echo provider internals). Model text from other stop reasons is kept.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { AgentResult } from "@cline/sdk";
import { outcomeFromResult } from "../../src/cline/adapter/turnOutcome.js";

function result(finishReason: AgentResult["finishReason"], text: string): AgentResult {
    return { finishReason, text } as AgentResult;
}

test("a provider error fails the run without using the error text as the answer", () => {
    const outcome = outcomeFromResult(result("error", "500 PROVIDER-SECRET-DETAIL"), null);
    assert.equal(outcome.finish, "failed");
    assert.equal(outcome.text, "");
    assert.equal(outcome.finish === "failed" ? outcome.reasonCode : null, "PROVIDER_ERROR");
});

test("model text is kept for completed and iteration-limited turns", () => {
    assert.equal(outcomeFromResult(result("completed", "답"), null).text, "답");
    assert.equal(outcomeFromResult(result("max_iterations", "중간 답"), null).text, "중간 답");
});

test("a host hook stop preserves its actionable failure while an ordinary SDK abort stays cancelled", () => {
    const stopped = outcomeFromResult(result("aborted", ""), { code: "SOURCE_CHANGED", message: "다시 색인하세요." });
    assert.deepEqual(stopped, {
        finish: "failed",
        text: "",
        reasonCode: "SOURCE_CHANGED",
        message: "다시 색인하세요.",
    });
    assert.equal(outcomeFromResult(result("aborted", ""), null).finish, "aborted");
});
