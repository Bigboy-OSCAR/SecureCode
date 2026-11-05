import { nodeBin, toolStep, uvStep } from "./processes.js";
import type { StepResult } from "./report.js";

export async function lintSteps(): Promise<StepResult[]> {
    return [await toolStep("lint: eslint", ...withArgs("eslint/bin/eslint.js", ["."]))];
}

export async function formatSteps(): Promise<StepResult[]> {
    return [await toolStep("format: prettier", ...withArgs("prettier/bin/prettier.cjs", ["--check", "."]))];
}

function withArgs(tool: string, args: string[]): [string, string[]] {
    const [node, script] = nodeBin(tool);
    return [node, [script, ...args]];
}

export async function typecheckSteps(): Promise<StepResult[]> {
    const results: StepResult[] = [];
    for (const project of ["contracts", "apps/host", "tools/sdk-probe", "scripts"]) {
        results.push(await toolStep(`types: ${project}`, ...withArgs("typescript/bin/tsc", ["-p", project])));
    }
    return results;
}

export async function generatedTypesSteps(): Promise<StepResult[]> {
    return [
        await toolStep("contracts: generated types fresh", process.execPath, [
            "--import",
            "tsx",
            "contracts/scripts/generateTypes.ts",
            "--check",
        ]),
    ];
}

export async function pythonStaticSteps(): Promise<StepResult[]> {
    return [
        await uvStep("lint: ruff", ["ruff", "check", "."]),
        await uvStep("format: ruff", ["ruff", "format", "--check", "."]),
        await uvStep("types: mypy", ["mypy", "src"]),
        await uvStep("convention: python docstrings", ["python", "../../scripts/check/python_docstrings.py"], 3, "4.3"),
    ];
}

export async function hostUnitSteps(): Promise<StepResult[]> {
    return [
        await toolStep("unit: host", process.execPath, [
            "--import",
            "tsx",
            "--test",
            "apps/host/tests/unit/**/*.test.ts",
        ]),
    ];
}

export async function pythonUnitSteps(): Promise<StepResult[]> {
    return [
        await uvStep("unit: context-service", ["pytest", "-q", "--ignore=tests/contract", "-m", "not integration"]),
    ];
}

export async function contractTestSteps(): Promise<StepResult[]> {
    return [
        await toolStep("contracts: fixtures (Ajv)", process.execPath, [
            "--import",
            "tsx",
            "--test",
            "contracts/tests/**/*.test.ts",
        ]),
        await uvStep("contracts: fixtures + service responses", ["pytest", "-q", "tests/contract"]),
    ];
}
