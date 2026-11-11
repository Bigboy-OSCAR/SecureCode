import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeProviderTools } from "../../src/cline/adapter/providerToolSchema.js";
import { createGatedFetch } from "../../src/cline/adapter/requestGateFetch.js";

test("counts and sends the same simplified tool grammar while preserving user data and original schemas", async () => {
    const original = {
        model: "local",
        messages: [{ role: "user", content: "maxLength is 2000" }],
        tools: [
            {
                type: "function",
                function: {
                    name: "search",
                    parameters: {
                        type: "object",
                        properties: { query: { type: "string", minLength: 1, maxLength: 2000 } },
                        required: ["query"],
                        additionalProperties: false,
                    },
                },
            },
        ],
    };
    const body = JSON.stringify(original);
    let counted = "";
    let sent = "";
    const gated = createGatedFetch({
        providerId: "openai-compatible",
        modelId: "local",
        maxOutputTokens: 10,
        allowedToolNames: new Set(["search"]),
        gate: {
            check: async (request) => {
                counted = request.body;
                return { allow: true, countedTokens: 5, countMode: "exact" };
            },
        },
        baseFetch: async (_input, init) => {
            assert.equal(typeof init?.body, "string");
            sent = init?.body as string;
            return new Response("{}");
        },
    });
    await gated("http://127.0.0.1:8080/v1/chat/completions", { method: "POST", body });
    assert.equal(sent, counted);
    const simplified = JSON.parse(sent) as typeof original;
    assert.equal(simplified.tools[0]?.function.parameters.properties.query.maxLength, undefined);
    assert.equal(simplified.tools[0]?.function.parameters.properties.query.minLength, 1);
    assert.equal(simplified.messages[0]?.content, "maxLength is 2000");
    assert.equal(original.tools[0]?.function.parameters.properties.query.maxLength, 2000);
    assert.equal(normalizeProviderTools(body, "anthropic"), body);
});
