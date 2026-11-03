/**
 * Writes the sanitized probe evidence file under the work root's
 * `artifacts/verification/3.1/`. Absolute paths and raw outputs are excluded.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ScenarioResult } from "./scenario-result.js";

const probeRootDir = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const workRootDir = join(probeRootDir, "..", "..");

export interface RepositoryGitState {
    refsDigest: string;
    stashEntries: number;
}

function readInstalledVersion(packageName: string): string {
    const packageJsonPath = join(probeRootDir, "node_modules", ...packageName.split("/"), "package.json");
    const manifest = JSON.parse(readFileSync(packageJsonPath, "utf8")) as { version?: string };
    return manifest.version ?? "unknown";
}

/** Read-only fingerprint of the team repository; used to show the probe changed no refs or stash. */
export function readRepositoryGitState(): RepositoryGitState {
    const runGit = (args: string[]): string => execFileSync("git", args, { cwd: workRootDir, encoding: "utf8" }).trim();
    const refs = runGit(["for-each-ref", "--format=%(refname) %(objectname)"]);
    const stash = runGit(["stash", "list"]);
    return {
        refsDigest: Buffer.from(refs).toString("base64url").slice(-24),
        stashEntries: stash.split("\n").filter(Boolean).length,
    };
}

export function writeEvidence(results: ScenarioResult[], gitBefore: RepositoryGitState, gitAfter: RepositoryGitState): string {
    const evidence = {
        task_id: "3.1",
        generated_at: new Date().toISOString(),
        node_version: process.version,
        platform: process.platform,
        packages: Object.fromEntries(
            ["@cline/sdk", "@cline/core", "@cline/agents", "@cline/llms", "@cline/shared", "typescript", "tsx"].map((name) => [name, readInstalledVersion(name)]),
        ),
        repository_git_unchanged: gitBefore.refsDigest === gitAfter.refsDigest && gitBefore.stashEntries === gitAfter.stashEntries,
        all_passed: results.every((result) => result.passed),
        scenarios: results,
    };
    const outputDir = join(workRootDir, "artifacts", "verification", "3.1");
    mkdirSync(outputDir, { recursive: true });
    const outputPath = join(outputDir, "sdk-probe-result.json");
    writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
    return "artifacts/verification/3.1/sdk-probe-result.json";
}
