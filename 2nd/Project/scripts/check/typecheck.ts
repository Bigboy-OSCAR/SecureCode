/** `npm run check:types`: TypeScript projects only (legacy host code reported as KNOWN). */
import { runAndExit } from "../lib/report.js";
import { typecheckSteps } from "../lib/steps.js";

await runAndExit("check:types", [typecheckSteps]);
