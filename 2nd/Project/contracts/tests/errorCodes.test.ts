/** The error table, the ErrorCode enum and the roadmap 0.6 required codes must stay in sync. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";
import { loadErrorCodeTable } from "../src/errorCodes.js";
import { resolveContractsRoot } from "../src/schemaFiles.js";

const ROADMAP_REQUIRED_CODES = [
    "INVALID_POINTER",
    "NOT_FOUND",
    "EXPIRED",
    "FORBIDDEN",
    "SOURCE_CHANGED",
    "INVALID_SELECTOR",
    "UNSUPPORTED_FORMAT",
    "UNSUPPORTED_LANGUAGE",
    "PARSE_FAILED",
    "NO_MATCH",
    "BUDGET_EXCEEDED",
    "TOKENIZER_UNAVAILABLE",
    "SDK_UNAVAILABLE",
    "PROVIDER_ERROR",
    "APPROVAL_REJECTED",
    "CANCELLED",
];

function readErrorCodeEnum(): string[] {
    const schemaPath = join(resolveContractsRoot(), "common", "api-error.schema.json");
    const schema = JSON.parse(readFileSync(schemaPath, "utf8")) as {
        definitions: { ErrorCode: { enum: string[] } };
    };
    return schema.definitions.ErrorCode.enum;
}

describe("error codes", () => {
    const enumCodes = readErrorCodeEnum();
    const table = loadErrorCodeTable();

    it("contain every roadmap 0.6 required code", () => {
        for (const code of ROADMAP_REQUIRED_CODES) {
            assert.ok(enumCodes.includes(code), code);
        }
    });

    it("have exactly one table row per enum value", () => {
        assert.deepEqual(Object.keys(table).sort(), [...enumCodes].sort());
    });

    it("use error-range HTTP statuses for error_response codes", () => {
        for (const [code, rule] of Object.entries(table)) {
            if (rule.transport === "error_response") {
                assert.ok(rule.http_status >= 400 && rule.http_status <= 599, code);
            } else {
                assert.equal(rule.http_status, 200, code);
            }
        }
    });
});
