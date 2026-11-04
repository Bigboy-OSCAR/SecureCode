/**
 * `npm run build`: verifies generated contracts, type-checks the host for
 * production and builds the context-service wheel. The UI build and local
 * packaging are PENDING, so the command exits 3 until 1.1/3.7 land.
 */
import { pendingResults } from "./lib/pendingSuites.js";
import { nodeBin, toolStep, uvCommand, isUvAvailable, SERVICE_DIR } from "./lib/processes.js";
import { runAndExit, type StepResult } from "./lib/report.js";
import { generatedTypesSteps } from "./lib/steps.js";
import { join } from "node:path";

async function hostBuildSteps(): Promise<StepResult[]> {
    const [nodePath, tscScript] = nodeBin(join("typescript", "bin", "tsc"));
    return [await toolStep("build: host types", nodePath, [tscScript, "--noEmit", "-p", "apps/host/tsconfig.json"])];
}

async function serviceBuildSteps(): Promise<StepResult[]> {
    if (!isUvAvailable()) {
        return [{ name: "build: context-service wheel", status: "FAIL", detail: "uv not found" }];
    }
    return [await toolStep("build: context-service wheel", uvCommand(), ["build", "--wheel"], { cwd: SERVICE_DIR })];
}

await runAndExit("build", [
    generatedTypesSteps,
    hostBuildSteps,
    serviceBuildSteps,
    () => Promise.resolve(pendingResults("build")),
]);
