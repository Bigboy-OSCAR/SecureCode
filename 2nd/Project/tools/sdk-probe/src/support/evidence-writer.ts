/**
 * Writes the sanitized probe evidence file under the work root's
 * `artifacts/verification/<task>/` (default task 3.1; set `SDK_PROBE_TASK_ID`
 * when a later task re-runs the probe). Absolute paths and raw outputs are excluded.
 */
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ScenarioResult } from "./scenario-result.js";

const probeRootDir = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const workRootDir = join(probeRootDir, "..", "..");
const evidenceTaskId = /^\d+\.\d+$/.test(process.env.SDK_PROBE_TASK_ID ?? "")
    ? (process.env.SDK_PROBE_TASK_ID as string)
    : "3.1";

export interface RepositoryGitState {
    refsDigest: string;
    stashEntries: number;
}

/**
 * Reads the version Node resolves for the probe. Workspace packages are hoisted
 * to the root, and `@cline/*` exports do not expose `package.json`, so the
 * node_modules directories are searched upward like Node's resolver does.
 */
function readInstalledVersion(packageName: string): string {
    for (let searchDir = probeRootDir; ; searchDir = dirname(searchDir)) {
        const packageJsonPath = join(searchDir, "node_modules", ...packageName.split("/"), "package.json");
        if (existsSync(packageJsonPath)) {
            const manifest = JSON.parse(readFileSync(packageJsonPath, "utf8")) as { version?: string };
            return manifest.version ?? "unknown";
        }
        if (dirname(searchDir) === searchDir) {
            return "unknown";
        }
    }
}

/** Read-only fingerprint of the team repository; used to show the probe changed no refs or stash. */
export function readRepositoryGitState(): RepositoryGitState {
    const runGit = (args: string[]): string => execFileSync("git", args, { cwd: workRootDir, encoding: "utf8" }).trim();
    const refs = runGit(["for-each-ref", "--format=%(refname) %(objectname)"]);
    const stash = runGit(["stash", "list", "--format=%H"]);
    return {
        refsDigest: createHash("sha256").update(refs).update("\0").update(stash).digest("hex"),
        stashEntries: stash.split("\n").filter(Boolean).length,
    };
}

export function writeEvidence(
    results: ScenarioResult[],
    gitBefore: RepositoryGitState,
    gitAfter: RepositoryGitState,
    partial: boolean,
): string {
    const evidence = {
        task_id: evidenceTaskId,
        generated_at: new Date().toISOString(),
        node_version: process.version,
        platform: process.platform,
        packages: Object.fromEntries(
            ["@cline/sdk", "@cline/core", "@cline/agents", "@cline/llms", "@cline/shared", "typescript", "tsx"].map(
                (name) => [name, readInstalledVersion(name)],
            ),
        ),
        repository_git_unchanged:
            gitBefore.refsDigest === gitAfter.refsDigest && gitBefore.stashEntries === gitAfter.stashEntries,
        all_passed: results.length > 0 && results.every((result) => result.passed),
        scenarios: results,
    };
    const outputDir = join(workRootDir, "artifacts", "verification", evidenceTaskId);
    mkdirSync(outputDir, { recursive: true });
    const fileName = partial ? "sdk-probe-partial-result.json" : "sdk-probe-result.json";
    const outputPath = join(outputDir, fileName);
    writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
    return `artifacts/verification/${evidenceTaskId}/${fileName}`;
}
