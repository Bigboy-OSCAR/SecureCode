/**
 * `npm run check:structure`: applies the structure rules to every tracked and
 * untracked-but-not-ignored file under the work root (read-only git listing),
 * plus the runtime import-cycle check. Baseline entries are KNOWN (open work of
 * another task); justified exceptions PASS with their recorded reason.
 */
import { execFileSync } from "node:child_process";
import { existsSync, lstatSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { printSummary, type StepResult } from "../lib/report.js";
import { WORK_ROOT } from "../lib/processes.js";
import { findBaselineEntry, findException, loadBaseline } from "./baseline.js";
import { secretRule } from "./contentRules.js";
import { findCycles, importEdges } from "./importGraph.js";
import { STRUCTURE_RULES, type FileUnderCheck, type Violation } from "./structureRules.js";

const TEXT_FILE = /\.(ts|tsx|js|mjs|cjs|py|md|json|ya?ml|toml|txt|html|css|cfg|ini|sh|ps1)$|(^|\/)\.env\.example$/;
const NOT_INSPECTED = /(^|\/)(package-lock\.json|uv\.lock)$/;

function listWorkRootFiles(): string[] {
    const output = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "."], {
        cwd: WORK_ROOT,
        encoding: "utf8",
    });
    return output.split("\0").filter(Boolean);
}

/** Secret-named values of the local, git-ignored .env; used only for matching and never printed. */
function localEnvSecrets(): string[] {
    const envFile = join(WORK_ROOT, ".env");
    if (!existsSync(envFile)) return [];
    return readFileSync(envFile, "utf8")
        .split(/\r?\n/)
        .map((line) => /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line))
        .filter((match) => match?.[1] && /(KEY|TOKEN|SECRET|PASSWORD)$/.test(match[1]))
        .map((match) => (match?.[2] ?? "").replace(/^["']|["']$/g, ""))
        .filter((value) => value.length >= 8);
}

export function readWorkRootFiles(): FileUnderCheck[] {
    const files: FileUnderCheck[] = [];
    for (const path of listWorkRootFiles()) {
        const fullPath = join(WORK_ROOT, path);
        // ls-files --cached also returns tracked files deleted in this worktree.
        // Inspect the current regular file only, without following a workspace symlink.
        if (!lstatSync(fullPath, { throwIfNoEntry: false })?.isFile()) continue;
        const inspect = TEXT_FILE.test(path) && !NOT_INSPECTED.test(path);
        files.push({ path, text: inspect ? readFileSync(fullPath, "utf8") : "" });
    }
    return files;
}

export function collectViolations(files: readonly FileUnderCheck[] = readWorkRootFiles()): Violation[] {
    const rules = [...STRUCTURE_RULES, secretRule(localEnvSecrets())];
    const violations = files.flatMap((file) => rules.flatMap((rule) => rule(file)));
    for (const cycle of findCycles(importEdges(files, WORK_ROOT))) {
        violations.push({ path: cycle[0] ?? "", rule: "import-cycle", message: `cycle: ${cycle.join(" -> ")}` });
    }
    return violations;
}

export function structureResults(): StepResult[] {
    const { entries, exceptions } = loadBaseline();
    const violations = collectViolations();
    const excepted = violations.filter((violation) => findException(exceptions, violation.rule, violation.path));
    const rest = violations.filter((violation) => !excepted.includes(violation));
    const known = rest.filter((violation) => findBaselineEntry(entries, violation.rule, violation.path));
    const unexpected = rest.filter((violation) => !known.includes(violation));

    for (const violation of unexpected) console.log(`FAIL  ${violation.rule}  ${violation.path}: ${violation.message}`);
    for (const violation of known) {
        const entry = findBaselineEntry(entries, violation.rule, violation.path);
        console.log(`KNOWN ${violation.rule}  ${violation.path}: ${violation.message} (owner ${entry?.task ?? "?"})`);
    }
    for (const violation of excepted) {
        const reason = findException(exceptions, violation.rule, violation.path)?.reason ?? "";
        console.log(`EXCEPT ${violation.rule}  ${violation.path}: ${reason}`);
    }

    const results: StepResult[] = [
        {
            name: "structure rules",
            status: unexpected.length > 0 ? "FAIL" : "PASS",
            detail:
                unexpected.length > 0
                    ? `${unexpected.length} new violation(s)`
                    : `no new violations (${excepted.length} documented exception(s))`,
        },
    ];
    if (known.length > 0) {
        const tasks = [...new Set(known.map((v) => findBaselineEntry(entries, v.rule, v.path)?.task))];
        results.push({
            name: "structure baseline",
            status: "KNOWN",
            detail: `${known.length} open violation(s) owned by other tasks`,
            ownerTask: tasks.join(","),
        });
    }
    return results;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
    process.exitCode = printSummary("check:structure", structureResults());
}
