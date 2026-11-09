/**
 * `npm run build`: verifies generated contracts, type-checks the host for
 * production, builds the UI and the context-service wheel. Local packaging
 * remains PENDING until 3.7 lands.
 */
import { pendingResults } from "./lib/pendingSuites.js";
import { nodeBin, toolStep, uvCommand, isUvAvailable, SERVICE_DIR } from "./lib/processes.js";
import { runAndExit, type StepResult } from "./lib/report.js";
import { generatedTypesSteps, uiBuildSteps } from "./lib/steps.js";
import { join } from "node:path";

async function hostBuildSteps(): Promise<StepResult[]> {
    const [nodePath, tscScript] = nodeBin(join("typescript", "bin", "tsc"));
    return [await toolStep("build: host types", nodePath, [tscScript, "--noEmit", "-p", "apps/host/tsconfig.json"])];
}

async function serviceBuildSteps(): Promise<StepResult[]> {
    if (!isUvAvailable()) {
        return [{ name: "build: context-service wheel", status: "FAIL", detail: "uv not found" }];
    }
    // uv builds the wheel from a fresh source archive, excluding stale files from a prior build.
    return [await toolStep("build: context-service wheel", uvCommand(), ["build"], { cwd: SERVICE_DIR })];
}

await runAndExit("build", [
    generatedTypesSteps,
    hostBuildSteps,
    uiBuildSteps,
    serviceBuildSteps,
    () => Promise.resolve(pendingResults("build")),
]);
