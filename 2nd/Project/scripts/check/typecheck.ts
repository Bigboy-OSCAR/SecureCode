/** `npm run check:types`: TypeScript projects only. */
import { runAndExit } from "../lib/report.js";
import { typecheckSteps } from "../lib/steps.js";

await runAndExit("check:types", [typecheckSteps]);
