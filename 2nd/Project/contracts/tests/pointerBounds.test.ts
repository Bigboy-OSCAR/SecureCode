import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { it } from "node:test";
import { ContractValidator } from "../src/validator.js";
import { SCHEMA_REFS } from "../src/schemaRefs.js";

const validator = ContractValidator.load();

for (const [fixture, field, limit] of [
    ["api/approval-korean-content.valid.json", "content", 16384],
    ["pointers/pointer-descriptor-source.valid.json", "preview", 512],
] as const) {
    it(`checks the UTF-8 boundary of ${field} on multibyte input`, () => {
        const { schema_ref: schemaRef, data } = JSON.parse(
            readFileSync(new URL(`../fixtures/${fixture}`, import.meta.url), "utf8"),
        ) as { schema_ref: string; data: Record<string, unknown> };
        const atLimit = "한".repeat(Math.floor(limit / 3)) + "a".repeat(limit % 3);
        assert.equal(Buffer.byteLength(atLimit), limit);
        assert.ok(validator.validate(schemaRef, { ...data, [field]: atLimit }).valid);
        assert.equal(validator.validate(schemaRef, { ...data, [field]: atLimit + "a" }).valid, false);
        assert.equal(validator.validate(schemaRef, { ...data, [field]: "\ud800" }).valid, false);
    });
}

it("rejects a 101st search match and a single chunk over the maximum read size", () => {
    const result = {
        schema_version: "1",
        pointer: "securecode://runtime/ws_00000001/ses_00000001/log_01?v=1",
        truncated: false,
        token_count: 0,
        count_mode: "provider_estimate",
    };
    const match = { line: 1, content: "x", byte_offset: 0 };
    const search = (matches: (typeof match)[]) =>
        validator.validate(SCHEMA_REFS.pointerSearchResult, { ...result, matches }).valid;
    assert.ok(search(Array.from({ length: 100 }, () => match)));
    assert.equal(search(Array.from({ length: 101 }, () => match)), false);
    assert.equal(search([{ ...match, content: "x".repeat(16385) }]), false);

    const read = (content: string) =>
        validator.validate(SCHEMA_REFS.pointerReadResult, {
            ...result,
            content,
            provenance: { media_type: "text/plain", byte_size: 16385, revision: 1 },
        }).valid;
    assert.ok(read("x".repeat(16384)));
    assert.equal(read("x".repeat(16385)), false);
});
