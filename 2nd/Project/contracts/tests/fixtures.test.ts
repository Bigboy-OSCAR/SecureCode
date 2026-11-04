/**
 * Validates every contract fixture against its schema with the runtime validator.
 * The Python service runs the same fixtures through jsonschema
 * (services/context-service/tests/contract/test_fixtures.py) so both languages agree.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { listFixtureFiles, resolveContractsRoot, toPosixRelative } from "../src/schemaFiles.js";
import { ContractValidator } from "../src/validator.js";

interface FixtureDocument {
    schema_ref: string;
    expect: "valid" | "invalid";
    scenario: string;
    data: unknown;
}

const contractsRoot = resolveContractsRoot();
const validator = ContractValidator.load(contractsRoot);
const fixtureFiles = listFixtureFiles(contractsRoot);

function readFixture(filePath: string): FixtureDocument {
    return JSON.parse(readFileSync(filePath, "utf8")) as FixtureDocument;
}

describe("contract fixtures", () => {
    it("exist for every owned area with both outcomes", () => {
        for (const area of ["common", "api", "events", "symbols", "pointers"]) {
            const names = fixtureFiles.map((file) => toPosixRelative(contractsRoot, file));
            assert.ok(
                names.some((name) => name.startsWith(`fixtures/${area}/`) && name.endsWith(".valid.json")),
                area,
            );
            assert.ok(
                names.some((name) => name.startsWith(`fixtures/${area}/`) && name.endsWith(".invalid.json")),
                area,
            );
        }
    });

    for (const filePath of fixtureFiles) {
        const name = toPosixRelative(contractsRoot, filePath);
        it(name, () => {
            const fixture = readFixture(filePath);
            assert.ok(name.endsWith(`.${fixture.expect}.json`), "file suffix must match expect");
            assert.match(fixture.scenario, /^(UI-\d{2}|H-\d{2}|\d\.\d{1,2})$/);
            const result = validator.validate(fixture.schema_ref, fixture.data);
            assert.equal(result.valid, fixture.expect === "valid", result.errors.join("\n"));
        });
    }
});
