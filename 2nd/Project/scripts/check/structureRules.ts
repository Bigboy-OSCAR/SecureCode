/**
 * Structure rules from roadmap 0.5 and docs/conventions/TYPESCRIPT_REACT.md.
 * Each rule inspects one tracked file (path + text) and returns violations.
 */
export interface Violation {
    path: string;
    rule: string;
    message: string;
}

export interface FileUnderCheck {
    path: string;
    text: string;
}

const PRODUCTION_LINE_LIMIT = 300;
const TEST_LINE_LIMIT = 500;
const SOURCE_EXTENSIONS = /\.(ts|tsx|js|mjs|py)$/;
const LINE_LIMIT_EXEMPT = /^(contracts\/generated\/|.*package-lock\.json$|.*uv\.lock$)/;
const HOST_SOURCE_DIRS = ["app", "routes", "cline", "context-client", "pointer-hooks", "config", "security", "logging"];
const SERVICE_PACKAGES = ["app", "api", "common", "symbols", "pointers", "context", "pdf"];

// Built from fragments so this file does not match its own patterns. Only string literals
// or argv arrays that would execute the command count; prose in comments does not.
const GIT_MUTATION = new RegExp(["[\"'`]", "git", "\\s+", "(commit|push)\\b"].join(""));
const GIT_ARGV_MUTATION = new RegExp(["\\[\\s*['\"]", "(commit|push)", "['\"]"].join(""));
const FORBIDDEN_IMPORTS = new RegExp(
    [
        "experiments/",
        "symbol_raptor",
        "runtime_pointer_bench",
        "source_pointer_bench",
        "symbol_bench",
        "sentence_transformers",
        "faiss",
        "chromadb",
        "\\braptor\\b",
        "sys\\.path\\.(insert|append)",
    ].join("|"),
    "i",
);

export function isTestPath(path: string): boolean {
    return /(^|\/)tests\//.test(path) || /\.test\.tsx?$/.test(path) || /(^|\/)test_[^/]+\.py$/.test(path);
}

function checkLineLimit(file: FileUnderCheck): Violation[] {
    if (!SOURCE_EXTENSIONS.test(file.path) || LINE_LIMIT_EXEMPT.test(file.path)) {
        return [];
    }
    const lines = file.text.split("\n").length - (file.text.endsWith("\n") ? 1 : 0);
    const limit = isTestPath(file.path) ? TEST_LINE_LIMIT : PRODUCTION_LINE_LIMIT;
    return lines > limit ? [{ path: file.path, rule: "max-lines", message: `${lines} lines > ${limit}` }] : [];
}

function checkPlacement(file: FileUnderCheck): Violation[] {
    const violations: Violation[] = [];
    const base = file.path.split("/").at(-1) ?? "";
    if (/^(temp|tmp|scratch|untitled|test\d+)\.(py|ts|js)$/i.test(base) || base.startsWith("tempCodeRunnerFile")) {
        violations.push({ path: file.path, rule: "temp-file", message: "temporary file in the product tree" });
    }
    const inProductionSource = /^(apps\/[^/]+\/src|services\/[^/]+\/src)\//.test(file.path);
    if (inProductionSource && /(^|\/)(test[-_][^/]*|[^/]+\.test\.tsx?|test_[^/]+\.py)$/.test(file.path)) {
        violations.push({ path: file.path, rule: "test-in-src", message: "test or experiment runner inside src/" });
    }
    const hostMatch = /^apps\/host\/src\/([^/]+)\//.exec(file.path);
    if (hostMatch?.[1] && !HOST_SOURCE_DIRS.includes(hostMatch[1])) {
        violations.push({ path: file.path, rule: "layout", message: `apps/host/src/${hostMatch[1]} is not in 0.5` });
    }
    const serviceMatch = /^services\/context-service\/src\/securecode_context\/([^/]+)\//.exec(file.path);
    if (serviceMatch?.[1] && !SERVICE_PACKAGES.includes(serviceMatch[1])) {
        violations.push({ path: file.path, rule: "layout", message: `package ${serviceMatch[1]} is not in 0.5` });
    }
    if (file.path.startsWith(".securecode/") || /\.(db|sqlite3)$/.test(file.path)) {
        violations.push({ path: file.path, rule: "runtime-data", message: "runtime data must not be committed" });
    }
    return violations;
}

function checkSourceContent(file: FileUnderCheck): Violation[] {
    if (!SOURCE_EXTENSIONS.test(file.path) || !/^(apps|services|scripts|tools|contracts)\//.test(file.path)) {
        return [];
    }
    const violations: Violation[] = [];
    if (GIT_MUTATION.test(file.text) || GIT_ARGV_MUTATION.test(file.text)) {
        violations.push({ path: file.path, rule: "git-mutation", message: "source must not run git commit/push" });
    }
    if (/^(apps|services)\//.test(file.path) && FORBIDDEN_IMPORTS.test(file.text)) {
        violations.push({
            path: file.path,
            rule: "forbidden-dependency",
            message: "experiment import, sys.path hack or out-of-scope retrieval library",
        });
    }
    if (file.path.startsWith("apps/ui/") && /@cline\/|\/internal\/v1|:8788\b/.test(file.text)) {
        violations.push({ path: file.path, rule: "ui-boundary", message: "UI must call only the host /api/v1" });
    }
    return violations;
}

function checkEnvExample(file: FileUnderCheck): Violation[] {
    if (file.path !== ".env.example") {
        return [];
    }
    const violations: Violation[] = [];
    for (const line of file.text.split("\n")) {
        const match = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
        if (!match?.[1]) {
            continue;
        }
        const [, name, value] = match;
        const secretName = /(^|_)(KEY|TOKEN|SECRET|PASSWORD)$/.test(name);
        if (secretName && (value ?? "").trim() !== "") {
            violations.push({ path: file.path, rule: "env-secret", message: `${name} must not have a value` });
        }
        if (name.startsWith("VITE_") && secretName) {
            violations.push({ path: file.path, rule: "env-secret", message: `${name}: secrets never use VITE_` });
        }
    }
    return violations;
}

export const STRUCTURE_RULES = [checkLineLimit, checkPlacement, checkSourceContent, checkEnvExample];
