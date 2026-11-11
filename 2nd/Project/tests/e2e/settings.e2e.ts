/** A genuinely unconfigured provider permits source preparation but blocks every question submission route. */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { buildIndex, registerProject } from "./support/uiActions.js";

let e2e: E2E;
before(async () => {
    e2e = await startE2E({ env: { SECURECODE_PROVIDER_API_KEY: "" } });
});
after(async () => {
    await e2e?.stop();
});

it("missing provider credentials leave project indexing available and block button and Enter submission", async () => {
    const { page, fake, files } = e2e;
    await registerProject(page, "prepare-only", files.projectDir);
    await buildIndex(page);
    await page.getByTestId("question-input").fill("모델 없이 실행하지 마세요");
    assert.ok(await page.getByTestId("question-submit").isDisabled());
    await page.getByTestId("question-input").press("Enter");
    assert.equal(fake.requests.length, 0);
    assert.equal(await page.getByTestId("answer").count(), 0);
    assert.match(await page.locator("#screen-chat").innerText(), /모델을 선택한 뒤/);
});
