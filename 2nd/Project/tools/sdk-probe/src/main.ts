/**
 * SDK probe entry: runs each scenario against the installed @cline/sdk and
 * writes a sanitized evidence file. Exits non-zero when any check fails.
 * Usage: `npm run probe` (all) or `npm run probe -- approval hook-failure`.
 */
import "./support/isolated-cline-home.js";
import { runApprovalScenario } from "./scenarios/approval.js";
import { runBeforeModelScenario } from "./scenarios/before-model.js";
import { runCheckpointScenario } from "./scenarios/checkpoint.js";
import { runHookFailureScenario } from "./scenarios/hook-failure.js";
import { runLifecycleScenario } from "./scenarios/lifecycle.js";
import { runOutboundGateScenario } from "./scenarios/outbound-gate.js";
import { runPointerReplacementScenario } from "./scenarios/pointer-replacement.js";
import { runRuntimeReadScenario } from "./scenarios/runtime-read.js";
import { runRuntimeSearchScenario } from "./scenarios/runtime-search.js";
import { runToolRestrictionScenario } from "./scenarios/tool-restriction.js";
import { readRepositoryGitState, writeEvidence } from "./support/evidence-writer.js";
import type { ScenarioResult } from "./support/scenario-result.js";

const scenarioRunners: Record<string, () => Promise<ScenarioResult>> = {
    lifecycle: runLifecycleScenario,
    "pointer-replacement": runPointerReplacementScenario,
    "runtime-read": runRuntimeReadScenario,
    "runtime-search": runRuntimeSearchScenario,
    approval: runApprovalScenario,
    "hook-failure": runHookFailureScenario,
    "before-model": runBeforeModelScenario,
    "outbound-gate": runOutboundGateScenario,
    "tool-restriction": runToolRestrictionScenario,
    checkpoint: runCheckpointScenario,
};

function printSummary(result: ScenarioResult): void {
    const failedChecks = result.checks.filter((record) => !record.passed);
    console.log(
        `${result.passed ? "PASS" : "FAIL"} ${result.scenario} (${result.checks.length - failedChecks.length}/${result.checks.length})`,
    );
    for (const record of failedChecks) {
        console.log(`  - FAILED ${record.name}: ${record.evidence}`);
    }
}

async function main(): Promise<void> {
    const args = process.argv.slice(2);
    const selected = args.filter((value) => value !== "--no-evidence");
    const unknown = selected.filter((name) => !Object.hasOwn(scenarioRunners, name));
    if (unknown.length > 0) {
        console.error("Unknown SDK probe scenario. Available:", Object.keys(scenarioRunners).join(", "));
        process.exitCode = 2;
        return;
    }
    const gitBefore = readRepositoryGitState();
    const results: ScenarioResult[] = [];

    for (const [name, runScenario] of Object.entries(scenarioRunners)) {
        if (selected.length > 0 && !selected.includes(name)) {
            continue;
        }
        const result = await runScenario();
        results.push(result);
        printSummary(result);
    }

    const gitAfter = readRepositoryGitState();
    const gitUnchanged =
        gitBefore.refsDigest === gitAfter.refsDigest && gitBefore.stashEntries === gitAfter.stashEntries;
    console.log(`repository refs/stash unchanged: ${gitUnchanged}`);
    if (!args.includes("--no-evidence")) {
        const evidencePath = writeEvidence(results, gitBefore, gitAfter, selected.length > 0);
        console.log(`evidence: ${evidencePath}`);
    }
    process.exitCode = results.length > 0 && results.every((result) => result.passed) && gitUnchanged ? 0 : 1;
}

await main();
