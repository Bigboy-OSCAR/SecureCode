/**
 * `npm run check`: lint, format, types, structure, conventions and unit tests for
 * every package. Exits 0 only when everything passes and nothing is KNOWN/PENDING.
 */
import { pendingResults } from "../lib/pendingSuites.js";
import { runAndExit } from "../lib/report.js";
import {
    formatSteps,
    generatedTypesSteps,
    hostUnitSteps,
    lintSteps,
    pythonStaticSteps,
    pythonUnitSteps,
    typecheckSteps,
    uiUnitSteps,
} from "../lib/steps.js";
import { structureResults } from "./structure.js";

await runAndExit("check", [
    lintSteps,
    formatSteps,
    typecheckSteps,
    () => Promise.resolve(structureResults()),
    generatedTypesSteps,
    pythonStaticSteps,
    hostUnitSteps,
    uiUnitSteps,
    pythonUnitSteps,
    () => Promise.resolve(pendingResults("check")),
]);
