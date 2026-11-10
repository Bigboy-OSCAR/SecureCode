/** `npm run test:unit`: host and context-service unit tests (no network, no processes). */
import { pendingResults } from "../lib/pendingSuites.js";
import { runAndExit } from "../lib/report.js";
import { hostUnitSteps, scriptUnitSteps, pythonUnitSteps, uiUnitSteps } from "../lib/steps.js";

await runAndExit("test:unit", [
    hostUnitSteps,
    scriptUnitSteps,
    uiUnitSteps,
    pythonUnitSteps,
    () => Promise.resolve(pendingResults("unit")),
]);
