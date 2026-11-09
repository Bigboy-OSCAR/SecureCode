/** Model names alone must never attest that a strict tokenizer exists. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { ModelRequestGate } from "../../src/pointer-hooks/model-gate.js";

for (const model of ["gpt-4", "claude-test", "unknown"]) {
    test(`strict gate blocks unverified tokenizer for ${model}`, () => {
        const result = new ModelRequestGate().validateRequest({
            model,
            systemPrompt: "system",
            userMessage: "안녕하세요",
            history: [],
            maxContextTokens: 128000,
            strictTokenizer: true,
        });
        assert.equal(result.allowed, false);
        assert.equal(result.reasonCode, "TOKENIZER_UNAVAILABLE");
    });
}
