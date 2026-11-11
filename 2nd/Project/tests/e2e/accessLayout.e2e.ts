/**
 * E2E (fixture provider): keyboard-only question and approval dialog (initial focus, Escape returns focus,
 * no decision on close), confirm dialogs, labelled pointer choices, and the 1280px / 768px layouts.
 */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import type { Page } from "playwright-core";
import { startE2E, type E2E } from "./support/e2eStack.js";
import {
    buildIndex,
    decideApproval,
    registerProject,
    registerSource,
    startSession,
    waitRunStatus,
} from "./support/uiActions.js";

let e2e: E2E;

before(async () => {
    e2e = await startE2E();
    await registerProject(e2e.page, "e2e-access", e2e.files.projectDir);
    await buildIndex(e2e.page);
    await startSession(e2e.page, "e2e-access");
});

after(async () => {
    await e2e?.stop();
});

function activeTestId(page: Page): Promise<string | null> {
    return page.evaluate(
        () => document.activeElement?.getAttribute("data-testid") ?? document.activeElement?.id ?? null,
    );
}

async function tabTo(page: Page, testId: string, limit = 80): Promise<void> {
    for (let i = 0; i < limit; i += 1) {
        if ((await activeTestId(page)) === testId) return;
        await page.keyboard.press("Tab");
    }
    throw new Error(`${testId} is not reachable with Tab`);
}

it("a question is asked and an approval dialog is handled with the keyboard alone", async () => {
    const { page, fake } = e2e;
    fake.script([{ tool: "run_command", args: { command: "node gen.js" } }, { text: "키보드로 처리했습니다." }]);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await tabTo(page, "question-input");
    await page.keyboard.type("키보드로 gen.js 를 실행해 주세요");
    await page.keyboard.press("Enter");
    await page.getByTestId("approval-meta").waitFor();

    await page.getByTestId("approval-approve").focus();
    await page.keyboard.press("Enter");
    await page.locator("dialog[open]").waitFor();
    assert.equal(await activeTestId(page), "modal-title", "the dialog opens on its title, not on a confirm button");
    await page.keyboard.press("Escape");
    await page.locator("dialog[open]").waitFor({ state: "detached" });
    assert.equal(await activeTestId(page), "approval-approve", "Escape returns focus to the opener");
    assert.equal(await page.getByTestId("approval-meta").count(), 1, "closing the dialog decided nothing");

    await decideApproval(page, "approve");
    await waitRunStatus(page, "완료");
    assert.match(
        await page.locator(".desk-run-status").ariaSnapshot(),
        /status: 완료/,
        "completion is exposed as a polite status live region",
    );
    assert.equal(
        await page.locator('[data-testid="answer"][aria-live], [data-testid="answer"] [aria-live]').count(),
        0,
        "streaming answer text is not announced token by token",
    );
});

it("confirm dialogs start on the title and return focus; pointer choices have accessible names", async () => {
    const { page, files } = e2e;
    await registerSource(page, files.bigLogPath, "big.log");
    assert.equal(await page.getByRole("radio", { name: /^big\.log · text\/plain/ }).count(), 1);
    const unregister = page
        .locator("li")
        .filter({ hasText: /^big\.log ·/ })
        .getByRole("button", { name: "등록 해제" });
    await unregister.focus();
    await page.keyboard.press("Enter");
    await page.locator("dialog[open]").waitFor();
    assert.equal(await activeTestId(page), "modal-title");
    await page.getByRole("button", { name: "돌아가기" }).click();
    await page.locator("dialog[open]").waitFor({ state: "detached" });
    assert.equal(await page.evaluate(() => document.activeElement?.textContent), "등록 해제");
    assert.equal(await page.getByRole("radio", { name: /^big\.log/ }).count(), 1, "going back kept the source");
});

async function horizontalOverflow(page: Page): Promise<number> {
    return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

it("1280px and narrow layouts preserve conversation, dismissible drawers and keyboard controls", async () => {
    const { page } = e2e;
    await page.setViewportSize({ width: 1280, height: 900 });
    assert.ok((await horizontalOverflow(page)) <= 0, "no horizontal page overflow at 1280px");
    assert.ok(await page.locator("#project-panel").isVisible());
    assert.ok(await page.locator("#context-panel").isVisible());
    await page.locator("#context-panel").getByRole("button", { name: "닫기", exact: true }).click();

    await page.setViewportSize({ width: 768, height: 900 });
    assert.ok((await horizontalOverflow(page)) <= 0, "no horizontal page overflow at 768px");
    assert.ok(await page.locator("#main-content").isVisible());
    assert.ok(await page.getByTestId("screen-approval").isVisible());
    assert.equal(await page.locator("#project-panel").isVisible(), false);
    assert.equal(await page.locator("#context-panel").isVisible(), false);
    const context = page.getByRole("button", { name: "자료 · 컨텍스트", exact: true });
    await context.focus();
    await page.keyboard.press("Enter");
    assert.ok(await page.locator("#context-panel").isVisible());
    assert.equal(await page.locator("#project-panel").isVisible(), false);
    await page.locator("#context-panel").getByRole("button", { name: "닫기", exact: true }).click();
    await page.setViewportSize({ width: 640, height: 900 });
    assert.ok((await horizontalOverflow(page)) <= 0, "no horizontal page overflow at 200% zoom (640px)");
    assert.ok(await page.getByTestId("question-submit").isVisible());
    await page.setViewportSize({ width: 1280, height: 900 });
});
