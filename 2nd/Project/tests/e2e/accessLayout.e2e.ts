/**
 * E2E (fixture provider): keyboard-only question and inline approval, confirm dialogs, labelled pointer
 * choices, and the 1280px / 768px layouts.
 */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import type { Page } from "playwright-core";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, buildIndex, registerProject, registerSource, startSession, waitRunStatus } from "./support/uiActions.js";

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

it("an approval appears only when requested and can be decided inline with the keyboard", async () => {
    const { page, fake } = e2e;
    assert.equal(await page.getByTestId("screen-approval").count(), 0, "there is no idle approval panel");
    fake.script([{ tool: "run_command", args: { command: "node gen.js" } }, { text: "키보드로 처리했습니다." }]);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await tabTo(page, "question-input");
    await page.keyboard.type("키보드로 gen.js 를 실행해 주세요");
    await page.keyboard.press("Enter");
    await page.getByTestId("approval-meta").waitFor();
    assert.equal(await activeTestId(page), "approval-heading", "the request focuses its heading, not a decision");
    assert.equal(await page.locator("dialog[open]").count(), 0, "an approval does not open a modal dialog");
    assert.equal(
        await page.locator('.desk-composer-wrap [data-testid="screen-approval"]').count(),
        1,
        "the request remains beside the composer instead of in the scrolling conversation",
    );
    await page.keyboard.press("Escape");
    assert.equal(await page.getByTestId("approval-meta").count(), 1, "Escape does not decide the request");
    await tabTo(page, "approval-approve");
    await page.keyboard.press("Enter");
    await waitRunStatus(page, "완료");
    assert.equal(await page.getByTestId("screen-approval").count(), 0, "the accepted request disappears");
    assert.equal(await page.locator("dialog[open]").count(), 0, "accepting needs no second confirmation dialog");
    assert.equal(await activeTestId(page), "question-input", "focus returns to the question after a decision");
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
    assert.equal(await page.getByTestId("screen-approval").count(), 0, "completed requests do not leave a panel");
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

it("a pending inline request keeps both decisions reachable on a narrow screen", async () => {
    const { page, fake } = e2e;
    fake.script([{ tool: "run_command", args: { command: "node gen.js" } }, { text: "실행하지 않았습니다." }]);
    await ask(page, "좁은 화면에서 실행 요청을 확인합니다");
    await page.getByTestId("approval-meta").waitFor();
    await page.setViewportSize({ width: 640, height: 680 });
    assert.ok((await horizontalOverflow(page)) <= 0, "the approval does not overflow the viewport");
    for (const testId of ["approval-approve", "approval-reject"]) {
        const box = await page.getByTestId(testId).boundingBox();
        assert.ok(box && box.x >= 0 && box.x + box.width <= 640 && box.y >= 0 && box.y + box.height <= 680);
    }
    await tabTo(page, "approval-reject");
    await page.keyboard.press("Enter");
    await waitRunStatus(page, "완료");
    assert.equal(await page.getByTestId("screen-approval").count(), 0, "the rejected request disappears");
    await page.setViewportSize({ width: 1280, height: 900 });
});
