/**
 * Reads scripts/check/structure-baseline.json: `entries` are open violations owned by another task
 * (KNOWN, the check stays INCOMPLETE); `exceptions` are permanent, justified exceptions (PASS with reason).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { WORK_ROOT } from "../lib/processes.js";

export interface BaselineEntry {
    path: string;
    rule: string;
    owner: string;
    task: string;
    note: string;
}

export interface StructureException {
    path: string;
    rule: string;
    reason: string;
}

export function loadBaseline(): { entries: BaselineEntry[]; exceptions: StructureException[] } {
    const raw = readFileSync(join(WORK_ROOT, "scripts", "check", "structure-baseline.json"), "utf8");
    const parsed = JSON.parse(raw) as { entries: BaselineEntry[]; exceptions?: StructureException[] };
    for (const exception of parsed.exceptions ?? []) {
        if (exception.reason.trim().length < 20) throw new Error(`exception for ${exception.path} needs a reason`);
    }
    return { entries: parsed.entries, exceptions: parsed.exceptions ?? [] };
}

export function pathMatches(entryPath: string, path: string): boolean {
    return entryPath.endsWith("/") ? path.startsWith(entryPath) : path === entryPath;
}

export function findBaselineEntry(
    entries: readonly BaselineEntry[],
    rule: string,
    path: string,
): BaselineEntry | undefined {
    return entries.find((entry) => entry.rule === rule && pathMatches(entry.path, path));
}

export function findException(
    exceptions: readonly StructureException[],
    rule: string,
    path: string,
): StructureException | undefined {
    return exceptions.find((exception) => exception.rule === rule && pathMatches(exception.path, path));
}
