/**
 * `npm run check:structure`: applies the structure rules to every tracked and
 * untracked-but-not-ignored file under the work root (read-only git listing).
 * Baseline-listed legacy violations are KNOWN; anything else FAILs.
 */
import { execFileSync } from "node:child_process";
import { lstatSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { printSummary, type StepResult } from "../lib/report.js";
import { WORK_ROOT } from "../lib/processes.js";
import { findBaselineEntry, loadBaseline } from "./baseline.js";
import { STRUCTURE_RULES, type Violation } from "./structureRules.js";

function listWorkRootFiles(): string[] {
    const output = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "."], {
        cwd: WORK_ROOT,
        encoding: "utf8",
    });
    return output.split("\0").filter(Boolean);
}

export function collectViolations(): Violation[] {
    const violations: Violation[] = [];
    for (const path of listWorkRootFiles()) {
        const fullPath = join(WORK_ROOT, path);
        // ls-files --cached also returns tracked files deleted in this worktree.
        // Inspect the current regular file only, without following a workspace symlink.
        if (!lstatSync(fullPath, { throwIfNoEntry: false })?.isFile()) continue;
        const inspectContent = /\.(?:ts|tsx|js|mjs|py)$/.test(path) || path === ".env.example";
        const file = { path, text: inspectContent ? readFileSync(fullPath, "utf8") : "" };
        for (const rule of STRUCTURE_RULES) {
            violations.push(...rule(file));
        }
    }
    return violations;
}

export function structureResults(): StepResult[] {
    const baseline = loadBaseline();
    const violations = collectViolations();
    const unexpected = violations.filter((violation) => !findBaselineEntry(baseline, violation.rule, violation.path));
    const known = violations.filter((violation) => findBaselineEntry(baseline, violation.rule, violation.path));

    for (const violation of unexpected) {
        console.log(`FAIL  ${violation.rule}  ${violation.path}: ${violation.message}`);
    }
    for (const violation of known) {
        const entry = findBaselineEntry(baseline, violation.rule, violation.path);
        console.log(`KNOWN ${violation.rule}  ${violation.path}: ${violation.message} (owner ${entry?.task ?? "?"})`);
    }

    const results: StepResult[] = [
        {
            name: "structure rules",
            status: unexpected.length > 0 ? "FAIL" : "PASS",
            detail: unexpected.length > 0 ? `${unexpected.length} new violation(s)` : "no new violations",
        },
    ];
    if (known.length > 0) {
        const tasks = [
            ...new Set(known.map((violation) => findBaselineEntry(baseline, violation.rule, violation.path)?.task)),
        ];
        results.push({
            name: "structure baseline",
            status: "KNOWN",
            detail: `${known.length} pre-3.2 violation(s) still open`,
            ownerTask: tasks.join(","),
        });
    }
    return results;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
    process.exitCode = printSummary("check:structure", structureResults());
}
