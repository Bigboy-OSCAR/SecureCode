/**
 * `npm run build`: verifies generated contracts, type-checks the host for
 * production, builds the UI and the context-service wheel, then checks both
 * artifacts and writes the local release manifest (3.7). Nothing is deployed.
 */
import { packagingSteps } from "./lib/packaging.js";
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

await runAndExit("build", [generatedTypesSteps, hostBuildSteps, uiBuildSteps, serviceBuildSteps, packagingSteps]);
