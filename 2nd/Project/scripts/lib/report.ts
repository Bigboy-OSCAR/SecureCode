/** Report real failures separately from incomplete roadmap work. */
export interface StepResult {
    name: string;
    status: "PASS" | "FAIL" | "KNOWN" | "PENDING" | "SKIPPED";
    detail: string;
    ownerTask?: string;
}

export function printSummary(command: string, results: readonly StepResult[]): number {
    for (const result of results) {
        console.log(
            `${result.status} ${result.name}: ${result.detail}${result.ownerTask ? ` [owner ${result.ownerTask}]` : ""}`,
        );
    }
    const code =
        !results.length || results.some((step) => step.status === "FAIL")
            ? 1
            : results.some((step) => step.status !== "PASS")
              ? 3
              : 0;
    console.log(`=== ${command}: ${code === 1 ? "FAILED" : code === 3 ? "INCOMPLETE" : "PASS"} (exit ${code}) ===`);
    return code;
}

export async function runAndExit(command: string, groups: readonly (() => Promise<StepResult[]>)[]): Promise<void> {
    const results: StepResult[] = [];
    for (const group of groups) {
        try {
            results.push(...(await group()));
        } catch (error) {
            results.push({
                name: group.name || command,
                status: "FAIL",
                detail: error instanceof Error ? error.message : "step failed",
            });
        }
    }
    process.exitCode = printSummary(command, results);
}
