/**
 * E2E (fixture provider): a context window smaller than the fixed request costs. The budget preview and
 * the question are both refused with BUDGET_EXCEEDED before any model request is sent.
 */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, buildIndex, registerProject, startSession } from "./support/uiActions.js";

let e2e: E2E;

before(async () => {
    // Output reserve (1024) + safety margin (1024) alone exceed what is left after system and tools.
    e2e = await startE2E({ contextLimit: 2100 });
    await registerProject(e2e.page, "e2e-budget", e2e.files.projectDir);
    await buildIndex(e2e.page);
    await startSession(e2e.page, "e2e-budget");
});

after(async () => {
    await e2e?.stop();
});

it("refuses the preview and the run with BUDGET_EXCEEDED and never calls the model", async () => {
    const { page, fake } = e2e;
    await page.getByLabel("예산을 확인할 실제 질문").fill("compute_invoice_total 을 설명해 주세요");
    await page.getByRole("button", { name: "컨텍스트 미리보기" }).click();
    await page.getByText("BUDGET_EXCEEDED · 입력 예산 초과").waitFor();

    await ask(page, "compute_invoice_total 을 설명해 주세요");
    await page
        .locator("#screen-chat")
        .getByText(/컨텍스트 예산을 초과/)
        .first()
        .waitFor();
    assert.equal(await page.getByTestId("answer").count(), 0, "no run was created");
    assert.equal(fake.requests.length, 0, "no request reached the model");
});
