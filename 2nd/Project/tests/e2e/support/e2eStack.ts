/**
 * One isolated E2E environment: fixture provider + the real `npm run dev` stack (context-service → host →
 * Vite UI) on free ports with a fresh data folder, and a headless browser already signed in with the
 * one-time launch code. The browser is the installed Edge/Chrome driven by playwright-core (no download);
 * SECURECODE_E2E_BROWSER (msedge|chrome) or SECURECODE_E2E_BROWSER_PATH selects another one.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium, type Browser, type Page } from "playwright-core";
import { startStack, type Stack } from "../../../scripts/lib/devStack.js";
import { findFreePorts } from "../../../scripts/lib/ports.js";
import { FAKE_MODEL_ID, startFakeLlama, type FakeLlama } from "./fakeLlama.js";
import { createWorkspaceFixture, type WorkspaceFixture } from "./workspaceFixture.js";

export interface E2EOptions {
    /** SECURECODE_MODEL_CONTEXT_LIMIT for budget tests (fixed costs alone are about 2.5k fake tokens). */
    contextLimit?: number;
    viewport?: { width: number; height: number };
    /** Extra host/service settings (e.g. a short approval timeout). */
    env?: Record<string, string>;
    /** Leave the browser on the connect screen (for launch-code tests). */
    skipLogin?: boolean;
}

export interface E2E {
    page: Page;
    launchCode: string;
    fake: FakeLlama;
    files: WorkspaceFixture;
    uiUrl: string;
    stop(): Promise<void>;
}

function launchBrowser(): Promise<Browser> {
    const executablePath = process.env.SECURECODE_E2E_BROWSER_PATH;
    if (executablePath) return chromium.launch({ executablePath, headless: true });
    const channel = process.env.SECURECODE_E2E_BROWSER ?? (process.platform === "win32" ? "msedge" : "chrome");
    return chromium.launch({ channel, headless: true });
}

export async function startE2E(options: E2EOptions = {}): Promise<E2E> {
    const fake = await startFakeLlama();
    const files = createWorkspaceFixture();
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-e2e-data-"));
    const ports = await findFreePorts();
    Object.assign(process.env, {
        SECURECODE_PROVIDER_ID: "openai-compatible",
        SECURECODE_MODEL_ID: FAKE_MODEL_ID,
        SECURECODE_PROVIDER_BASE_URL: fake.baseUrl,
        SECURECODE_PROVIDER_API_KEY: "e2e-fixture-provider",
        SECURECODE_TOKEN_COUNTER: "llama-cpp",
        SECURECODE_REQUIRE_FINAL_TOKEN_COUNT: "true",
        SECURECODE_MODEL_CONTEXT_LIMIT: String(options.contextLimit ?? 32768),
        SECURECODE_MAX_OUTPUT_TOKENS: "1024",
        SECURECODE_CONTEXT_SAFETY_MARGIN_TOKENS: "1024",
        SECURECODE_UI_DEV_PORT: String(ports.uiPort),
        SECURECODE_LOG_LEVEL: "warn",
        SECURECODE_APPROVAL_TIMEOUT_MS: "300000",
        ...options.env,
    });
    let stack: Stack | undefined;
    let browser: Browser | undefined;
    const stop = async (): Promise<void> => {
        await browser?.close().catch(() => undefined);
        await stack?.stopAll().catch(() => undefined);
        await fake.close();
        for (const dir of [dataDir, files.projectDir, files.externalDir, files.polyglotDir]) {
            rmSync(dir, { recursive: true, force: true, maxRetries: 5 });
        }
    };
    try {
        stack = await startStack({
            ...ports,
            dataDir,
            onOutput: process.env.E2E_LOG ? (name, line) => console.log(`[${name}]`, line) : () => undefined,
        });
        browser = await launchBrowser();
        const page = await browser.newPage({ viewport: options.viewport ?? { width: 1280, height: 900 } });
        page.setDefaultTimeout(20000);
        await page.goto(stack.ui.uiUrl);
        const launchCode = stack.services.bootstrapCode;
        if (!options.skipLogin) {
            await page.getByLabel("연결 코드").fill(launchCode);
            await page.getByRole("button", { name: "연결", exact: true }).click();
            await page.getByText("호스트 상태: ok").waitFor();
        }
        return { page, launchCode, fake, files, uiUrl: stack.ui.uiUrl, stop };
    } catch (error) {
        await stop();
        throw error;
    }
}
