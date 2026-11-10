/** Each 3.7 structure rule must fire on a violating file and stay quiet on a clean one (no no-op checks). */
import assert from "node:assert/strict";
import { test } from "node:test";
import { checkOutOfScope, checkPlaceholders, checkProductionMocks, secretRule } from "../check/contentRules.js";
import { findCycles, importEdges } from "../check/importGraph.js";
import { WORK_ROOT } from "../lib/processes.js";

// Built from fragments so this file itself never trips the rules it tests.
const join = (...parts: string[]): string => parts.join("");
const rules = (violations: { rule: string }[]): string[] => violations.map((violation) => violation.rule);

test("placeholder rule finds stubs in product sources only", () => {
    const stub = { path: "apps/host/src/routes/x.ts", text: join("throw new Error('not ", "implemented');") };
    assert.deepEqual(rules(checkPlaceholders(stub)), ["placeholder"]);
    const python = {
        path: "services/context-service/src/securecode_context/x.py",
        text: join("raise NotImpl", "ementedError"),
    };
    assert.deepEqual(rules(checkPlaceholders(python)), ["placeholder"]);
    const status = { path: "apps/host/src/a.ts", text: join('status: "not_', 'implemented"') };
    assert.deepEqual(rules(checkPlaceholders(status)), ["placeholder"]);
    assert.deepEqual(checkPlaceholders({ path: "apps/host/tests/a.test.ts", text: stub.text }), []);
    assert.deepEqual(checkPlaceholders({ path: "apps/host/src/b.ts", text: "export const ok = 1;" }), []);
});

test("production-mock rule flags test doubles and fixture imports inside src", () => {
    const module = checkProductionMocks({ path: "apps/ui/src/api/fakeClient.ts", text: "" });
    assert.deepEqual(rules(module), ["production-mock"]);
    const imported = checkProductionMocks({
        path: "apps/host/src/a.ts",
        text: join('import x from "../../../contracts/', 'fixtures/api/a.json";'),
    });
    assert.deepEqual(rules(imported), ["production-mock"]);
    const python = checkProductionMocks({
        path: "services/context-service/src/securecode_context/a.py",
        text: join("from unittest.", "mock import MagicMock"),
    });
    assert.deepEqual(rules(python), ["production-mock"]);
    assert.deepEqual(checkProductionMocks({ path: "apps/host/tests/support/fakeRuntime.ts", text: "" }), []);
});

test("secret rule finds key shapes and local .env values without printing them", () => {
    const key = join("sk-", "ant-", "api03-", "Q".repeat(30));
    const found = secretRule([])({ path: "docs/a.md", text: `key ${key}` });
    assert.deepEqual(rules(found), ["secret"]);
    assert.doesNotMatch(found[0]?.message ?? "", /QQQQ/);
    const local = join("local-", "value-", "1234");
    assert.deepEqual(rules(secretRule([local])({ path: "README.md", text: `x ${local}` })), ["secret"]);
    assert.deepEqual(secretRule([local])({ path: "README.md", text: "SECURECODE_PROVIDER_API_KEY=" }), []);
});

test("out-of-scope rule blocks experiment imports and excluded techniques", () => {
    const experiment = { path: "scripts/lib/a.ts", text: join('import x from "../../', "experiments/", 'x.js";') };
    assert.deepEqual(rules(checkOutOfScope(experiment)), ["forbidden-dependency"]);
    const technique = { path: "services/context-service/src/securecode_context/a.py", text: join("import ", "faiss") };
    assert.deepEqual(rules(checkOutOfScope(technique)), ["forbidden-dependency"]);
    const embedding = { path: "apps/host/src/a.ts", text: join("client.embeddings", ".create({})") };
    assert.deepEqual(rules(checkOutOfScope(embedding)), ["forbidden-dependency"]);
    assert.deepEqual(checkOutOfScope({ path: "apps/host/src/a.ts", text: 'import { x } from "./x.js";' }), []);
});

test("import graph finds TypeScript and Python cycles and ignores type-only imports", () => {
    assert.deepEqual(
        findCycles(
            new Map([
                ["a", ["b"]],
                ["b", ["c"]],
                ["c", ["a"]],
                ["d", ["a"]],
            ]),
        ),
        [["a", "b", "c"]],
    );
    assert.deepEqual(
        findCycles(
            new Map([
                ["a", ["b"]],
                ["b", []],
            ]),
        ),
        [],
    );
    const edges = importEdges(
        [
            {
                path: "scripts/lib/ports.ts",
                text: 'import type { X } from "./services.js";\nimport { a } from "./readiness.js";',
            },
            {
                path: "services/context-service/src/securecode_context/api/health.py",
                text: "from securecode_context.common import tokens\nif TYPE_CHECKING:\n    from securecode_context.app import factory\n",
            },
        ],
        WORK_ROOT,
    );
    assert.deepEqual(edges.get("scripts/lib/ports.ts"), ["scripts/lib/readiness.ts"]);
    assert.ok(
        edges
            .get("services/context-service/src/securecode_context/api/health.py")
            ?.some((t) => t.endsWith("common/tokens/__init__.py")),
    );
    assert.ok(
        !edges.get("services/context-service/src/securecode_context/api/health.py")?.some((t) => t.includes("factory")),
    );
});
