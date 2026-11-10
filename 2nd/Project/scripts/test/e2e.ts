/**
 * `npm run test:e2e`: browser end-to-end flows (UI-01..UI-34) are written by 1.6. Until a runner is
 * registered here this reports PENDING (exit 3), never PASS. The stack it will drive (`npm run dev`:
 * service -> host -> UI with the /api proxy) is covered by scripts/test/devLifecycle.test.ts.
 */
import { pendingResults } from "../lib/pendingSuites.js";
import { runAndExit } from "../lib/report.js";

await runAndExit("test:e2e", [() => Promise.resolve(pendingResults("e2e"))]);
