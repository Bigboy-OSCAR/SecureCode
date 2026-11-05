/**
 * `npm run test:live`: opt-in smoke against the real provider. Requires
 * SECURECODE_LIVE_SMOKE=1 and ANTHROPIC_API_KEY in the server environment (.env).
 * Without them the run is SKIPPED (exit 3), never PASS. The 3.2 live check is
 * tokens.count on the shared Unicode vectors; SDK runs are PENDING for 3.6.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ContractValidator, SCHEMA_REFS, type TokenCountResult } from "@securecode/contracts";
import { pendingResults } from "../lib/pendingSuites.js";
import { WORK_ROOT } from "../lib/processes.js";
import { runAndExit, type StepResult } from "../lib/report.js";
import { findFreePorts, startServices } from "../lib/services.js";

interface UnicodeCase {
    name: string;
    text: string;
    expect: string;
    utf8_bytes?: number;
}

const envFile = join(WORK_ROOT, ".env");
if (existsSync(envFile)) {
    process.loadEnvFile(envFile);
}

function liveGate(): StepResult | null {
    if (process.env.SECURECODE_LIVE_SMOKE !== "1") {
        return { name: "live smoke", status: "SKIPPED", detail: "SECURECODE_LIVE_SMOKE is not 1 (opt-in)" };
    }
    if (!process.env.ANTHROPIC_API_KEY?.trim()) {
        return { name: "live smoke", status: "SKIPPED", detail: "ANTHROPIC_API_KEY is not set" };
    }
    return null;
}

async function liveTokenCountSteps(): Promise<StepResult[]> {
    const gate = liveGate();
    if (gate) {
        return [gate];
    }
    const maxCalls = Number(process.env.SECURECODE_LIVE_SMOKE_MAX_CALLS ?? "10");
    if (!Number.isSafeInteger(maxCalls) || maxCalls < 0) {
        return [{ name: "live smoke", status: "FAIL", detail: "MAX_CALLS must be a nonnegative integer" }];
    }
    if (maxCalls === 0) return [{ name: "live smoke", status: "SKIPPED", detail: "call budget is zero" }];
    const vectors = JSON.parse(
        readFileSync(join(WORK_ROOT, "tests", "fixtures", "token-unicode-cases.json"), "utf8"),
    ) as {
        cases: UnicodeCase[];
    };
    const cases = vectors.cases.filter((item) => item.expect === "valid").slice(0, maxCalls);
    const validator = ContractValidator.load();
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-live-"));
    let services;
    try {
        services = await startServices({
            ...(await findFreePorts()),
            dataDir,
        });
    } catch (error) {
        rmSync(dataDir, { recursive: true, force: true });
        throw error;
    }
    const results: StepResult[] = [];
    try {
        for (const vector of cases) {
            const response = await fetch(`${services.serviceUrl}/internal/v1/tokens/count`, {
                method: "POST",
                headers: { authorization: `Bearer ${services.internalToken}`, "content-type": "application/json" },
                body: JSON.stringify({ text: vector.text }),
            });
            const body: unknown = await response.json();
            const valid = response.ok && validator.validate(SCHEMA_REFS.tokenCountResult, body).valid;
            const result = body as TokenCountResult;
            const passed = valid && result.count_mode === "provider_estimate" && result.token_count > 0;
            const detail = valid ? `${result.token_count} tokens (${result.count_mode})` : `HTTP ${response.status}`;
            results.push({ name: `live tokens.count ${vector.name}`, status: passed ? "PASS" : "FAIL", detail });
        }
    } finally {
        await services.stopAll();
        rmSync(dataDir, { recursive: true, force: true });
    }
    return results;
}

await runAndExit("test:live", [liveTokenCountSteps, () => Promise.resolve(pendingResults("live"))]);
