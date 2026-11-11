/** Pointer selection scopes both displayed results and user-entered ranges/searches. */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, buildIndex, registerProject, registerSource, selectPointer, waitRunStatus } from "./support/uiActions.js";
let e2e: E2E;
before(async () => {
    e2e = await startE2E();
});
after(async () => {
    await e2e?.stop();
});
it("switching from a text source to a PDF clears the old range and search", async () => {
    const { page, files } = e2e;
    await registerProject(page, "pointer-switch", files.projectDir);
    await registerSource(page, files.bigLogPath, "big.log");
    await selectPointer(page, "big.log");
    await page.getByLabel("시작 줄", { exact: true }).fill("25000");
    await page.getByLabel("끝 범위 (선택)", { exact: true }).fill("26000");
    await page.getByLabel("포인터 내용 검색", { exact: true }).fill("LOG-TARGET");
    await registerSource(page, files.pdfPath, "manual.pdf");
    await selectPointer(page, "manual.pdf");
    assert.equal(await page.getByLabel("시작 페이지", { exact: true }).inputValue(), "1");
    assert.equal(await page.getByLabel("끝 범위 (선택)", { exact: true }).inputValue(), "");
    assert.equal(await page.getByLabel("포인터 내용 검색", { exact: true }).inputValue(), "");
    await selectPointer(page, "big.log");
    assert.equal(await page.getByLabel("시작 줄", { exact: true }).inputValue(), "1");
    assert.equal(await page.title(), "LocalDesk");
});

it("a PDF page selected in the drawer reaches the actual run after the drawer is closed", async () => {
    const { page, fake } = e2e;
    await page.locator("#context-panel").getByRole("button", { name: "닫기", exact: true }).click();
    await buildIndex(page);
    await page.getByRole("button", { name: "자료 · 컨텍스트", exact: true }).click();
    await selectPointer(page, "manual.pdf");
    await page.getByRole("button", { name: "PDF parse job 시작" }).click();
    await page.getByText(/ready · 원본 3쪽/).waitFor({ timeout: 60000 });
    await page.getByLabel("시작 페이지", { exact: true }).fill("2");
    await page.getByRole("button", { name: "범위 읽기", exact: true }).click();
    await page.getByText("PAGE-TWO-SENTINEL", { exact: false }).first().waitFor();
    await page.locator("#context-panel").getByRole("button", { name: "닫기", exact: true }).click();
    await page.locator(".desk-context-chip").filter({ hasText: "원본 PDF 2쪽" }).waitFor();
    fake.script([{ text: "선택한 문서 2쪽을 확인했습니다." }]);
    const request = page.waitForRequest(
        (item) => item.method() === "POST" && /\/sessions\/[^/]+\/runs$/.test(item.url()),
    );
    await ask(page, "지금 선택한 PDF 2쪽의 내용은?");
    const payload: unknown = (await request).postDataJSON();
    assert.ok(payload && typeof payload === "object" && "context_refs" in payload);
    const refs = payload.context_refs;
    assert.ok(Array.isArray(refs));
    assert.equal(refs.length, 1);
    await waitRunStatus(page, "완료");
    assert.match(fake.requests.at(-1) ?? "", /PAGE-TWO-SENTINEL/);
    assert.doesNotMatch(fake.requests.at(-1) ?? "", /PAGE-ONE-SENTINEL|PAGE-THREE-SENTINEL/);
    assert.match(await page.getByTestId("answer-citations").innerText(), /원본 PDF 2쪽/);
});
