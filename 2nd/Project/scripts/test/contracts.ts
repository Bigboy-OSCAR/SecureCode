/**
 * `npm run test:contracts`: every fixture through Ajv (TS) and jsonschema (Python),
 * real service responses against the schemas, and generated-type freshness.
 */
import { pendingResults } from "../lib/pendingSuites.js";
import { runAndExit } from "../lib/report.js";
import { contractTestSteps, generatedTypesSteps } from "../lib/steps.js";

await runAndExit("test:contracts", [
    generatedTypesSteps,
    contractTestSteps,
    () => Promise.resolve(pendingResults("contracts")),
]);
