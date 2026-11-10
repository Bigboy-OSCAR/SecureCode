/**
 * Content rules added in 3.7: unimplemented placeholders, production mocks, committed secrets,
 * experiment imports and out-of-scope retrieval techniques. Patterns are assembled from fragments
 * so this file never matches itself.
 */
import type { FileUnderCheck, Violation } from "./structureRules.js";

const words = (...parts: string[]): RegExp => new RegExp(parts.join(""));
const PRODUCT_SOURCE = /^(apps\/[^/]+\/src|services\/[^/]+\/src|tools\/[^/]+\/src|contracts\/src|scripts\/(dev|lib))\//;
const APP_SOURCE = /^(apps\/[^/]+\/src|services\/[^/]+\/src)\//;
const CODE = /\.(ts|tsx|js|mjs|py)$/;

const PLACEHOLDERS: readonly [RegExp, string][] = [
    [words("\\b(TO", "DO|FIX", "ME|X", "XX)\\b"), "unfinished-work marker"],
    [words("NotImplemented", "Error"), "Python stub raising the not-implemented error"],
    [words("throw new Error\\([^)]*not ", "implemented"), "TypeScript stub throwing not-implemented"],
    [words("[\"']not_", "implemented[\"']"), "hard-coded not-implemented status"],
];

/** Module names and import targets that mean test doubles are part of the shipped product. */
const MOCK_FILE = words("(^|/)[^/]*(fixture|mock|fake|stub)[^/]*\\.(ts|tsx|py)$");
const MOCK_IMPORT = words(
    "(from\\s+[\"'][^\"']*(contracts/fixtures/|/tests/|[^/\"']*(fixture|mock|fake)[^/\"']*[\"'])",
    "|^\\s*(from|import)\\s+(unittest\\.mock|tests\\.|pytest))",
);

const SECRET_PATTERNS: readonly [RegExp, string][] = [
    [words("sk-", "ant-[A-Za-z0-9_-]{20,}"), "Anthropic API key"],
    [words("\\bsk-", "(proj-)?[A-Za-z0-9]{32,}"), "OpenAI-style API key"],
    [words("\\bAK", "IA[0-9A-Z]{16}\\b"), "AWS access key"],
    [words("\\bgh", "[pousr]_[A-Za-z0-9]{36,}"), "GitHub token"],
    [words("\\bxox", "[abpr]-[A-Za-z0-9-]{10,}"), "Slack token"],
    [words("-----BEGIN [A-Z ]*PRIVATE ", "KEY-----"), "private key"],
];

const OUT_OF_SCOPE = words(
    "experiments/|(^|[\"'/])1st/|symbol_raptor|_pointer_bench|symbol_bench",
    "|sentence_transformers|faiss|chromadb|\\braptor\\b|self[_-]?extend|summary[_-]?tree",
    "|embeddings?\\.create|text-embedding|embed_(query|documents)|llm[_-]?selector",
    "|sys\\.path\\.(insert|append)",
);
const IMPORT_LINE = /^\s*(import|from|export)\b.*$|require\([^)]*\)|import\([^)]*\)/gm;

export function checkPlaceholders(file: FileUnderCheck): Violation[] {
    if (!PRODUCT_SOURCE.test(file.path) || !CODE.test(file.path)) return [];
    return PLACEHOLDERS.filter(([pattern]) => pattern.test(file.text)).map(([, message]) => ({
        path: file.path,
        rule: "placeholder",
        message,
    }));
}

export function checkProductionMocks(file: FileUnderCheck): Violation[] {
    if (!APP_SOURCE.test(file.path) || !CODE.test(file.path)) return [];
    const violations: Violation[] = [];
    if (MOCK_FILE.test(file.path)) {
        violations.push({ path: file.path, rule: "production-mock", message: "test double module inside src/" });
    }
    if (file.text.split("\n").some((line) => MOCK_IMPORT.test(line))) {
        violations.push({ path: file.path, rule: "production-mock", message: "src imports fixtures, mocks or tests" });
    }
    return violations;
}

/** Scans every inspected text file; `envSecrets` are the local .env secret values, never printed. */
export function secretRule(envSecrets: readonly string[]): (file: FileUnderCheck) => Violation[] {
    return (file) => {
        const violations = SECRET_PATTERNS.filter(([pattern]) => pattern.test(file.text)).map(([, kind]) => ({
            path: file.path,
            rule: "secret",
            message: `looks like a committed ${kind}`,
        }));
        if (envSecrets.some((value) => file.text.includes(value))) {
            violations.push({
                path: file.path,
                rule: "secret",
                message: "contains a secret value from the local .env",
            });
        }
        return violations;
    };
}

export function checkOutOfScope(file: FileUnderCheck): Violation[] {
    if (!/^(apps|services|scripts|tools|contracts)\//.test(file.path) || !CODE.test(file.path)) return [];
    if (file.path.startsWith("scripts/check/")) return [];
    const imports = file.text.match(IMPORT_LINE) ?? [];
    const inAppCode = APP_SOURCE.test(file.path) && OUT_OF_SCOPE.test(file.text);
    if (!inAppCode && !imports.some((line) => OUT_OF_SCOPE.test(line))) return [];
    return [
        {
            path: file.path,
            rule: "forbidden-dependency",
            message: "experiment/1st import, sys.path hack or a technique outside R0/Source/Runtime pointers",
        },
    ];
}
