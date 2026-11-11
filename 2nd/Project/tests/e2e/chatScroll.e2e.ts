/** Chat restoration and incoming updates preserve the reader's intended scroll position. */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, buildIndex, registerProject, waitRunStatus } from "./support/uiActions.js";

let e2e: E2E;
before(async () => {
    e2e = await startE2E();
    await registerProject(e2e.page, "chat-scroll", e2e.files.projectDir);
    await buildIndex(e2e.page);
});
after(async () => {
    await e2e?.stop();
});

async function atBottom(): Promise<void> {
    await e2e.page.waitForFunction(() => {
        const messages = document.querySelector(".desk-messages");
        return messages && messages.scrollHeight - messages.clientHeight - messages.scrollTop < 5;
    });
}

async function scrollToEarlierAnswer(): Promise<void> {
    await e2e.page.locator(".desk-messages").hover();
    await e2e.page.mouse.wheel(0, -10000);
    await e2e.page.waitForFunction(() => (document.querySelector(".desk-messages")?.scrollTop ?? -1) < 5);
}

it("long replies and restored conversations show the latest turn", async () => {
    const { page, fake } = e2e;
    fake.script([
        { text: Array.from({ length: 45 }, (_, index) => `문단 ${index + 1}: 기존 답변 내용입니다.`).join("\n\n") },
    ]);
    await ask(page, "긴 답변을 확인합니다");
    await waitRunStatus(page, "완료");
    await atBottom();
    const height = await page
        .locator(".desk-messages")
        .evaluate((element) => element.scrollHeight - element.clientHeight);
    assert.ok(height > 500, "the conversation genuinely exceeds the visible chat area");
    await scrollToEarlierAnswer();
    await page.reload();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    await waitRunStatus(page, "완료");
    await atBottom();
});

it("sending from an older turn follows the new question but later reading stays in place", async () => {
    const { page, fake } = e2e;
    await scrollToEarlierAnswer();
    fake.script([{ hold: true }]);
    await ask(page, "새 질문은 아래에서 보여야 합니다");
    await waitRunStatus(page, "실행 중");
    await atBottom();
    await scrollToEarlierAnswer();
    await page.getByTestId("run-cancel").click();
    await waitRunStatus(page, "취소됨");
    const top = await page.locator(".desk-messages").evaluate((element) => element.scrollTop);
    assert.ok(top < 5, "a run status update must not pull a reader away from an earlier answer");
});
