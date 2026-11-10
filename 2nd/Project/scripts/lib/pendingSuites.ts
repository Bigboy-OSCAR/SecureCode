import type { StepResult } from "./report.js";

interface PendingSuite {
    command: string;
    name: string;
    ownerTask: string;
    detail: string;
}
export const PENDING_SUITES: readonly PendingSuite[] = [
    { command: "e2e", name: "UI end-to-end flows", ownerTask: "1.6", detail: "browser workflow runner pending" },
];
export function pendingResults(command: string): StepResult[] {
    return PENDING_SUITES.filter((suite) => suite.command === command).map((suite) => ({
        ...suite,
        status: "PENDING",
    }));
}
