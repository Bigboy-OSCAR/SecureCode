import type { StepResult } from "./report.js";

interface PendingSuite {
    command: string;
    name: string;
    ownerTask: string;
    detail: string;
}
// Empty since 1.6 registered the browser E2E runner (2026-11-11); kept for later suites.
export const PENDING_SUITES: readonly PendingSuite[] = [];
export function pendingResults(command: string): StepResult[] {
    return PENDING_SUITES.filter((suite) => suite.command === command).map((suite) => ({
        ...suite,
        status: "PENDING",
    }));
}
