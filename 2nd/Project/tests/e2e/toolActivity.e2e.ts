/** Each answer owns its collapsible activity, including previous turns restored after reload. */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import type { Locator } from "playwright-core";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, decideApproval, registerProject, waitRunStatus } from "./support/uiActions.js";

let e2e: E2E;
const FIRST = "첫 질문의 파일 목록을 확인해 주세요";
const SECOND = "두 번째 질문에서 명령을 실행해 주세요";
const THIRD = "세 번째 질문에는 도구 없이 답해 주세요";

function turn(question: string): Locator {
    return e2e.page.getByTestId("conversation-turn").filter({ has: e2e.page.getByText(question, { exact: true }) });
}

before(async () => {
    e2e = await startE2E();
    await registerProject(e2e.page, "tool-activity", e2e.files.projectDir);
});
after(async () => {
    await e2e?.stop();
});

it("activity belongs to each answer, expands during work, and remains available after later turns and reload", async () => {
    const { page, fake } = e2e;
    fake.script([{ tool: "list_files", args: {} }, { text: "첫 번째 답변입니다." }]);
    await ask(page, FIRST);
    await waitRunStatus(page, "완료");
    const first = turn(FIRST);
    const firstActivity = first.getByTestId("tool-history");
    await firstActivity.waitFor();
    await firstActivity.getByTestId("tool-row").waitFor({ state: "hidden" });
    assert.equal(await firstActivity.getAttribute("open"), null, "completed activity starts collapsed");
    assert.match(await firstActivity.locator("summary").first().innerText(), /이 답변의 작업/);
    assert.ok(
        await first.evaluate((element) => {
            const activity = element.querySelector('[data-testid="tool-history"]');
            const answer = element.querySelector('[data-testid="answer"]');
            return (
                !!activity &&
                !!answer &&
                !!(activity.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING)
            );
        }),
        "the activity is attached before its own answer",
    );
    const requestsBeforeToggle = fake.requests.length;
    await firstActivity.locator("summary").first().focus();
    await page.keyboard.press("Enter");
    await firstActivity.getByTestId("tool-row").waitFor();
    assert.match(await firstActivity.getByTestId("tool-row").innerText(), /파일 목록/);
    await page.keyboard.press("Enter");
    assert.equal(await firstActivity.getAttribute("open"), null);
    assert.equal(fake.requests.length, requestsBeforeToggle, "opening activity never reruns a tool");

    fake.script([{ tool: "run_command", args: { command: "node gen.js" } }, { text: "두 번째 답변입니다." }]);
    await ask(page, SECOND);
    await page.getByTestId("approval-meta").waitFor();
    const second = turn(SECOND);
    const secondActivity = second.getByTestId("tool-history");
    assert.notEqual(await secondActivity.getAttribute("open"), null, "active work opens its own activity");
    await secondActivity.getByTestId("tool-row").waitFor();
    assert.match(await secondActivity.getByTestId("tool-row").innerText(), /명령 실행/);
    assert.doesNotMatch(await secondActivity.innerText(), /파일 목록/, "the new turn does not inherit earlier tools");
    await decideApproval(page, "reject");
    await waitRunStatus(page, "완료");
    await secondActivity.getByTestId("tool-row").waitFor({ state: "hidden" });
    assert.equal(await secondActivity.getAttribute("open"), null, "finished work collapses");
    await secondActivity.locator("summary").first().click();
    assert.match(await secondActivity.getByTestId("tool-row").innerText(), /거절됨/);
    assert.equal(await first.getByTestId("tool-row").count(), 1, "earlier activity remains with the first answer");
    assert.equal(await second.getByTestId("tool-row").count(), 1);

    fake.script([{ text: "세 번째 답변입니다." }]);
    await ask(page, THIRD);
    await waitRunStatus(page, "완료");
    const third = turn(THIRD);
    assert.equal(await third.getByTestId("tool-history").count(), 0, "no empty expandable panel without tools");
    assert.match(await third.innerText(), /도구 사용 없음/);
    assert.equal(await third.getByTestId("tool-row").count(), 0);
    const requestsBeforeReload = fake.requests.length;
    await page.reload();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    await turn(THIRD).getByTestId("answer").getByText("세 번째 답변입니다.", { exact: true }).waitFor();
    assert.equal(await page.getByTestId("conversation-turn").count(), 3);
    assert.equal(await turn(FIRST).getByTestId("tool-row").count(), 1);
    assert.equal(await turn(SECOND).getByTestId("tool-row").count(), 1);
    assert.equal(await turn(THIRD).getByTestId("tool-row").count(), 0);
    await turn(FIRST).getByTestId("tool-history").locator("summary").first().click();
    assert.match(await turn(FIRST).getByTestId("tool-row").innerText(), /파일 목록/);
    await turn(SECOND).getByTestId("tool-history").locator("summary").first().click();
    assert.match(await turn(SECOND).getByTestId("tool-row").innerText(), /명령 실행/);
    assert.equal(fake.requests.length, requestsBeforeReload, "restoring history never repeats execution");
});
