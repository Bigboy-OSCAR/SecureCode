import type { StepResult } from "./report.js";

interface PendingSuite {
    command: string;
    name: string;
    ownerTask: string;
    detail: string;
}
export const PENDING_SUITES: readonly PendingSuite[] = [
    { command: "dev", name: "web UI", ownerTask: "1.1", detail: "UI package pending" },
    { command: "check", name: "UI lint and types", ownerTask: "1.1", detail: "UI package pending" },
    { command: "unit", name: "UI behaviour tests", ownerTask: "1.3", detail: "UI package pending" },
    {
        command: "integration",
        name: "R0 workspace search/bundle",
        ownerTask: "3.6",
        detail: "Python R0SymbolService ready (3.4); host route connection pending",
    },
    {
        command: "integration",
        name: "runtime/source pointer",
        ownerTask: "4.3–4.6",
        detail: "contract service integration pending",
    },
    {
        command: "integration",
        name: "context selector and request gate",
        ownerTask: "4.8",
        detail: "provider integration pending",
    },
    { command: "integration", name: "PDF parse/read", ownerTask: "4.9", detail: "PDF service pending" },
    { command: "e2e", name: "UI end-to-end flows", ownerTask: "1.6", detail: "browser workflow pending" },
    { command: "live", name: "SDK run against provider", ownerTask: "3.6", detail: "live provider smoke pending" },
    { command: "build", name: "UI production build", ownerTask: "1.1", detail: "UI package pending" },
    { command: "build", name: "local packaging", ownerTask: "3.7", detail: "distribution pending" },
];
export function pendingResults(command: string): StepResult[] {
    return PENDING_SUITES.filter((suite) => suite.command === command).map((suite) => ({
        ...suite,
        status: "PENDING",
    }));
}
