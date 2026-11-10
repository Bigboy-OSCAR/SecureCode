/**
 * `npm run test:install`: fresh-install smoke (3.7). Needs network access for npm and uv (or warm caches)
 * and takes several minutes; it is separate from the offline `test:integration` and the provider `test:live`.
 */
import { mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import {
    api,
    copyWorkTree,
    installSteps,
    login,
    portsClosed,
    startDev,
    step,
    stopDev,
    type InstallCopy,
} from "../lib/installSmoke.js";
import { WORK_ROOT } from "../lib/processes.js";
import { runAndExit, type StepResult } from "../lib/report.js";

/** Names and mtimes of the user's own data directory, to prove the smoke never touched it. */
function userDataFingerprint(): string {
    const dir = join(WORK_ROOT, ".securecode");
    try {
        return readdirSync(dir)
            .map((name) => `${name}:${statSync(join(dir, name)).mtimeMs}`)
            .join("|");
    } catch {
        return "absent";
    }
}

async function lifecycle(copy: InstallCopy): Promise<StepResult[]> {
    const results: StepResult[] = [];
    const first = await startDev(copy);
    results.push(step("start: service -> host -> UI ready", true, "UI page served, launch code printed"));
    let cookie = await login(copy, first.code);
    const root = join(copy.root, "sample-workspace");
    mkdirSync(root);
    const created = await api(copy, cookie, "POST", "/api/v1/workspaces", {
        display_name: "install smoke",
        root_path: root,
        idempotency_key: "install-smoke-ws",
    });
    results.push(
        step("use: login and register a workspace via the UI proxy", created.status === 201, `HTTP ${created.status}`),
    );
    const stopped = stopDev(copy);
    results.push(
        step("stop: npm run stop", stopped === 0 && (await portsClosed(copy)), `exit ${stopped}, ports closed`),
    );

    const second = await startDev(copy);
    cookie = await login(copy, second.code);
    const listed = await api(copy, cookie, "GET", "/api/v1/workspaces");
    const kept = JSON.stringify(listed.body).includes("install smoke");
    results.push(
        step(
            "restart: data survives in the same data directory",
            listed.status === 200 && kept,
            `HTTP ${listed.status}`,
        ),
    );
    const health = await api(copy, cookie, "GET", "/api/v1/health");
    const components = JSON.stringify(health.body);
    results.push(
        step(
            "restart: health ok with real feature components",
            /"status":"ok"/.test(components) && !components.includes("not_implemented"),
            components.slice(0, 160),
        ),
    );
    const again = stopDev(copy);
    results.push(step("stop after restart", again === 0 && (await portsClosed(copy)), `exit ${again}`));
    return results;
}

const before = userDataFingerprint();
const copy = await copyWorkTree();
console.log(`install smoke copy: ${copy.root}`);
await runAndExit("test:install", [
    () => Promise.resolve(installSteps(copy)),
    async () => {
        try {
            return await lifecycle(copy);
        } finally {
            stopDev(copy);
        }
    },
    () => Promise.resolve([step("user data untouched", userDataFingerprint() === before, "work-root .securecode")]),
]);
if (process.exitCode === 0) rmSync(copy.root, { recursive: true, force: true, maxRetries: 5 });
else console.log(`kept for diagnosis: ${copy.root}`);
