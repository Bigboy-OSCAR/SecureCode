/**
 * Collects named checks for one scenario. Evidence values must be short and
 * must not contain raw tool output, credentials, or absolute personal paths.
 */

export interface CheckRecord {
    name: string;
    passed: boolean;
    evidence: string;
}

export interface ScenarioResult {
    scenario: string;
    passed: boolean;
    checks: CheckRecord[];
    observations: Record<string, unknown>;
}

export class ScenarioRecorder {
    private readonly checks: CheckRecord[] = [];
    private readonly observations: Record<string, unknown> = {};

    constructor(private readonly scenario: string) {}

    check(name: string, passed: boolean, evidence: string): void {
        this.checks.push({ name, passed, evidence });
    }

    observe(key: string, value: unknown): void {
        this.observations[key] = value;
    }

    fail(name: string, error: unknown): void {
        const kind = error instanceof Error ? error.name : "UnknownError";
        this.check(name, false, `scenario raised ${kind}`);
    }

    finish(): ScenarioResult {
        const passed = this.checks.length > 0 && this.checks.every((record) => record.passed);
        return { scenario: this.scenario, passed, checks: this.checks, observations: this.observations };
    }
}
