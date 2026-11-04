import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createLogger } from "../../src/logging/logger.js";
import { Redactor } from "../../src/logging/redaction.js";
import { loadSharedVectors } from "../support/sharedFixtures.js";

interface RedactionVectors {
    max_chars: number;
    cases: { name: string; input: string; secrets: string[]; expected: string }[];
}

const vectors = loadSharedVectors<RedactionVectors>("redaction-cases.json");

describe("redaction (shared vectors with Python)", () => {
    for (const vector of vectors.cases) {
        it(vector.name, () => {
            assert.equal(new Redactor(vector.secrets, vectors.max_chars).redact(vector.input), vector.expected);
        });
    }

    it("applies to every logger level, debug included", () => {
        const lines: string[] = [];
        const logger = createLogger("debug", new Redactor(["internal-token-value-0000"]), (line) => lines.push(line));
        logger.debug("token internal-token-value-0000 sent with Bearer abcdefghijklmnop");
        assert.equal(lines.length, 1);
        assert.ok(!lines[0]?.includes("internal-token-value-0000"));
        assert.ok(lines[0]?.includes("Bearer [REDACTED]"));
    });
});
