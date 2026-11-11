/**
 * `npm run test:e2e`: browser end-to-end flows (1.6) against the real stack (context-service → host → Vite UI)
 * with the fixture provider in tests/e2e/support/fakeLlama.ts. Each file starts its own stack on free
 * ports with a temporary data folder. The browser is the installed Edge/Chrome (playwright-core, no
 * download); SECURECODE_E2E_BROWSER=msedge|chrome or SECURECODE_E2E_BROWSER_PATH picks another.
 * A real provider is exercised separately by `npm run test:live`, never here.
 */
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { toolStep, WORK_ROOT } from "../lib/processes.js";
import { runAndExit } from "../lib/report.js";

const E2E_DIR = join("tests", "e2e");
const files = readdirSync(join(WORK_ROOT, E2E_DIR))
    .filter((name) => name.endsWith(".e2e.ts"))
    .sort()
    .map((name) => join(E2E_DIR, name));

await runAndExit("test:e2e", [
    async () => [
        await toolStep("UI end-to-end flows (fixture provider, real stack, headless browser)", process.execPath, [
            "--import",
            "tsx",
            "--test",
            "--test-concurrency=1",
            ...files,
        ]),
    ],
]);
