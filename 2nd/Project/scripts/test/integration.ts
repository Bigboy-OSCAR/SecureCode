/**
 * `npm run test:integration`: real processes on loopback. Covers the service
 * process test and the host -> context-service health chain, including the
 * degraded path when the service stops. Unbuilt suites are PENDING.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ContractValidator, SCHEMA_REFS } from "@securecode/contracts";
import { pendingResults } from "../lib/pendingSuites.js";
import { runAndExit, type StepResult } from "../lib/report.js";
import { findFreePort, startServices } from "../lib/services.js";
import { uvStep } from "../lib/processes.js";

const validator = ContractValidator.load();

function expectStep(name: string, passed: boolean, detail: string): StepResult {
    return { name, status: passed ? "PASS" : "FAIL", detail };
}

async function hostServiceChainSteps(): Promise<StepResult[]> {
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-it-"));
    const results: StepResult[] = [];
    let services;
    try {
        services = await startServices({ hostPort: await findFreePort(), servicePort: await findFreePort(), dataDir });
    } catch (error) {
        rmSync(dataDir, { recursive: true, force: true });
        return [
            expectStep("chain: start host + service", false, error instanceof Error ? error.message : "start failed"),
        ];
    }
    try {
        results.push(expectStep("chain: start host + service", true, "both healthy on 127.0.0.1"));

        const okBody: unknown = await (await fetch(`${services.hostUrl}/api/v1/health`)).json();
        const okValid = validator.validate(SCHEMA_REFS.healthResponse, okBody).valid;
        results.push(
            expectStep(
                "chain: host health ok",
                okValid && JSON.stringify(okBody).includes('"ok"'),
                JSON.stringify(okBody),
            ),
        );

        const anonymous = await fetch(`${services.serviceUrl}/internal/v1/health`);
        results.push(
            expectStep("chain: service rejects no token", anonymous.status === 401, `HTTP ${anonymous.status}`),
        );

        const pending = await fetch(`${services.hostUrl}/api/v1/sessions`, {
            method: "POST",
            headers: { origin: services.hostUrl },
        });
        results.push(expectStep("chain: unbuilt route is 501", pending.status === 501, `HTTP ${pending.status}`));

        await services.stopService();
        const degradedBody: unknown = await (await fetch(`${services.hostUrl}/api/v1/health`)).json();
        const degraded = JSON.stringify(degradedBody) === JSON.stringify({ schema_version: "1", status: "degraded" });
        results.push(expectStep("chain: host degraded when service stops", degraded, JSON.stringify(degradedBody)));
    } finally {
        await services.stopAll();
        rmSync(dataDir, { recursive: true, force: true });
    }
    return results;
}

await runAndExit("test:integration", [
    async () => [await uvStep("service process (pytest -m integration)", ["pytest", "-q", "-m", "integration"])],
    hostServiceChainSteps,
    () => Promise.resolve(pendingResults("integration")),
]);
