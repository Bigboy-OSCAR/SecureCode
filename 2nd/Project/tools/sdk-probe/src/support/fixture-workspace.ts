/**
 * Creates a throwaway Git workspace inside the isolated probe home and reads a
 * Git state fingerprint (status, refs, stash) to detect SDK checkpoint writes.
 * The probe only runs `git init` and read-only Git commands.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { probeHomeDir } from "./isolated-cline-home.js";

export interface GitFingerprint {
    status: string;
    refs: string;
    stash: string;
}

function runGit(cwd: string, args: string[]): string {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

export function createFixtureWorkspace(name: string): string {
    const workspaceDir = join(probeHomeDir, "workspaces", name);
    mkdirSync(workspaceDir, { recursive: true });
    writeFileSync(join(workspaceDir, "app.py"), "def handler():\n    return 1\n", "utf8");
    runGit(workspaceDir, ["init", "--quiet"]);
    return workspaceDir;
}

export function readGitFingerprint(workspaceDir: string): GitFingerprint {
    return {
        status: runGit(workspaceDir, ["status", "--porcelain", "--untracked-files=all"]),
        refs: runGit(workspaceDir, ["for-each-ref", "--format=%(refname)"]),
        stash: runGit(workspaceDir, ["stash", "list"]),
    };
}
