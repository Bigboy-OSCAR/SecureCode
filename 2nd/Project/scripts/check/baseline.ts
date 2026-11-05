/** Reads scripts/check/structure-baseline.json and matches violations against it. */
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

export function loadBaseline(): BaselineEntry[] {
    const raw = readFileSync(join(WORK_ROOT, "scripts", "check", "structure-baseline.json"), "utf8");
    return (JSON.parse(raw) as { entries: BaselineEntry[] }).entries;
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
