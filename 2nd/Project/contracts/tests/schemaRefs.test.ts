/** Every named ref used by the host resolves, and no schema file fails to compile. */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { loadSchemaFiles } from "../src/schemaFiles.js";
import { SCHEMA_REFS } from "../src/schemaRefs.js";
import { ContractValidator } from "../src/validator.js";

describe("schema refs", () => {
    const validator = ContractValidator.load();

    for (const [name, ref] of Object.entries(SCHEMA_REFS)) {
        it(`${name} resolves`, () => {
            assert.doesNotThrow(() => validator.validate(ref, {}));
        });
    }

    it("compile every definition of every schema file", () => {
        for (const file of loadSchemaFiles()) {
            const definitions = Object.keys(file.schema.definitions ?? {});
            for (const definitionName of definitions) {
                assert.doesNotThrow(
                    () => validator.validate(`${file.relativePath}#/definitions/${definitionName}`, null),
                    `${file.relativePath}#${definitionName}`,
                );
            }
        }
    });
});
