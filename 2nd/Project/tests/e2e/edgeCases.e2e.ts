/**
 * E2E (fixture provider): launch-code errors, a rejected project path, a five-language project with a
 * broken file, the send button during an active run, a provider failure, approval expiry, an invalid
 * read range and a PDF changed after parsing.
 */
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { join } from "node:path";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import {
    ask,
    buildIndex,
    contextPanelText,
    registerProject,
    registerSource,
    selectPointer,
    startSession,
    waitRunStatus,
} from "./support/uiActions.js";

const APPROVAL_TIMEOUT_MS = 4000;
let e2e: E2E;

before(async () => {
    e2e = await startE2E({ skipLogin: true, env: { SECURECODE_APPROVAL_TIMEOUT_MS: String(APPROVAL_TIMEOUT_MS) } });
});

after(async () => {
    await e2e?.stop();
});

it("a wrong launch code is refused; the right one connects and is kept nowhere in the page", async () => {
    const { page, launchCode } = e2e;
    await page.locator(".desk-connect-prompt").getByRole("button", { name: "연결 설정" }).click();
    await page.getByLabel("연결 코드").fill("wrong-code-123456");
    await page.getByRole("button", { name: "연결", exact: true }).click();
    await page.locator("[role=alert]").first().waitFor();
    assert.equal(await page.getByText("호스트 상태: ok").count(), 0);
    assert.match(
        (await page.locator("[role=alert]").allInnerTexts()).join(" "),
        /연결 코드를 확인하고 다시 입력하세요/,
    );

    await page.getByLabel("연결 코드").fill(launchCode);
    await page.getByRole("button", { name: "연결", exact: true }).click();
    await page.getByText("호스트 상태: ok").waitFor();
    assert.equal(await page.getByLabel("연결 코드").inputValue(), "", "the code field is cleared");
    const stored = await page.evaluate(() => [
        location.href,
        JSON.stringify({ ...localStorage }),
        JSON.stringify({ ...sessionStorage }),
        document.cookie,
    ]);
    for (const value of stored)
        assert.ok(!value.includes(launchCode), "the launch code is not in URL, storage or readable cookies");
    await page.getByRole("button", { name: "대화상자 닫기" }).click();
});

it("a project path that does not exist is refused next to the form and not listed", async () => {
    const { page, files } = e2e;
    await page.getByRole("button", { name: "+ 프로젝트 추가", exact: true }).click();
    await page.getByTestId("project-path").fill(join(files.projectDir, "does-not-exist"));
    await page.getByTestId("project-name").fill("missing");
    await page.getByTestId("project-register").click();
    await page.locator("dialog [role=alert]").first().waitFor();
    assert.match(
        (await page.locator("dialog [role=alert]").allInnerTexts()).join(" "),
        /경로가 존재하지 않습니다/,
        "the reason is named, not a generic policy refusal",
    );
    assert.equal(await page.locator(".desk-projects").getByRole("button", { name: "missing", exact: true }).count(), 0);
    await page.getByRole("button", { name: "대화상자 닫기" }).click();
});

it("a five-language project with a broken file reports what was indexed and what failed", async () => {
    const { page, files } = e2e;
    await registerProject(page, "polyglot", files.polyglotDir);
    await page.getByRole("button", { name: "인덱스 생성·갱신", exact: true }).click();
    await page.getByTestId("index-start").click();
    await page
        .locator("dialog .desk-job")
        .getByText(/부분 완료|partial/)
        .first()
        .waitFor({ timeout: 60000 });
    const status = await page.locator("dialog .desk-job").innerText();
    assert.match(status, /부분 완료|partial/, "a partial index is not shown as a full success");
    assert.match(status, /발견 7 · 색인 5 · 제외 1 · 실패 1/, "C, C++, Java, JavaScript and Python files were indexed");
    assert.match(status, /broken.py:1 · syntax_error/);
    assert.match(status, /types.ts · unsupported_language/);
    await page.getByRole("button", { name: "대화상자 닫기" }).click();
});

it("the send button is locked while a run is active", async () => {
    const { page, fake, files } = e2e;
    await registerProject(page, "e2e-edge", files.projectDir);
    await buildIndex(page);
    await startSession(page, "e2e-edge");
    fake.script([{ hold: true }]);
    await ask(page, "오래 걸리는 질문");
    await waitRunStatus(page, "실행 중");
    await page.getByTestId("question-input").fill("두 번째 질문");
    assert.ok(await page.getByTestId("question-submit").isDisabled(), "no second run while one is active");
    await page.getByTestId("run-cancel").click();
    await waitRunStatus(page, "취소됨", 15000);
});

it("a provider outage fails the run with a safe message instead of a false completion", async () => {
    const { page, fake } = e2e;
    fake.script(Array.from({ length: 8 }, () => ({ status: 500 })));
    await ask(page, "모델 오류를 일으키는 질문");
    await waitRunStatus(page, "실패", 120000);
    const chat = await page.locator("#screen-chat").innerText();
    assert.doesNotMatch(chat, /FIXTURE-PROVIDER-SECRET-DETAIL/, "the provider body is not shown");
    assert.doesNotMatch(chat, /no scripted turn/);
});

it("an approval left undecided expires and the command never runs", async () => {
    const { page, fake } = e2e;
    fake.script([{ tool: "run_command", args: { command: "node gen.js" } }, { text: "만료 뒤 답" }]);
    await ask(page, "승인 만료를 확인합니다");
    await page.getByTestId("approval-meta").waitFor();
    await waitRunStatus(page, "완료", APPROVAL_TIMEOUT_MS + 30000);
    assert.equal(await page.getByTestId("screen-approval").count(), 0, "the expired request disappears");
    assert.equal(await page.getByTestId("approval-meta").count(), 0, "no decision is offered after expiry");
    assert.match((await page.getByTestId("tool-row").allInnerTexts()).join(" "), /run_command expired/);
    assert.doesNotMatch(fake.requests.join(" "), /BULK-LOG-/, "the expired command produced no output");
});

it("an inverted read range is explained before any request", async () => {
    const { page, files } = e2e;
    await registerSource(page, files.bigLogPath, "big.log");
    await selectPointer(page, "big.log");
    await page.getByLabel("시작 줄").fill("10");
    await page.getByLabel("끝 범위 (선택)").fill("5");
    await page.getByRole("button", { name: "범위 읽기" }).click();
    await page.getByText("끝 줄은 시작 줄(10)보다 작을 수 없습니다.").waitFor();
});

it("a PDF changed after parsing discards the old page and asks for a refresh", async () => {
    const { page, files } = e2e;
    await registerSource(page, files.pdfPath, "manual.pdf");
    await selectPointer(page, "manual.pdf");
    await page.getByRole("button", { name: "PDF parse job 시작" }).click();
    await page.getByText(/ready · 원본 3쪽/).waitFor({ timeout: 60000 });
    appendFileSync(files.pdfPath, "% changed after parsing");
    await page.getByLabel("시작 페이지").fill("2");
    await page.getByRole("button", { name: "범위 읽기" }).click();
    await page.getByText("이 미리보기는 폐기했습니다. Source 목록에서 등록 갱신 후 다시 읽으세요.").waitFor();
    assert.doesNotMatch(await contextPanelText(page), /PAGE-TWO-SENTINEL/, "no page text from the old file");
});
