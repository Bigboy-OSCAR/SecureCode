/**
 * E2E (fixture provider): rejection, cancel keeping the run's history, an SSE drop with automatic
 * reconnection, a source edited after indexing (stale), and a PDF without a text layer.
 */
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import {
    ask,
    buildIndex,
    contextPanelText,
    decideApproval,
    openCurrentToolActivity,
    registerProject,
    registerSource,
    selectPointer,
    startSession,
    waitRunStatus,
} from "./support/uiActions.js";

let e2e: E2E;

before(async () => {
    e2e = await startE2E();
    await registerProject(e2e.page, "e2e-failures", e2e.files.projectDir);
    await buildIndex(e2e.page);
    await startSession(e2e.page, "e2e-failures");
});

after(async () => {
    await e2e?.stop();
});

it("a rejected command never runs and the run reports the rejection", async () => {
    const { page, fake } = e2e;
    fake.script([
        { tool: "run_command", args: { command: "node gen.js" } },
        { text: "명령이 거절되어 실행하지 않았습니다." },
    ]);
    await ask(page, "gen.js 를 실행해 주세요");
    await page.getByTestId("approval-meta").waitFor();
    await decideApproval(page, "reject");
    await waitRunStatus(page, "완료");
    assert.equal(await page.getByTestId("screen-approval").count(), 0, "the rejected request disappears");
    const tools = await (await openCurrentToolActivity(page)).getByTestId("tool-row").allInnerTexts();
    assert.ok(
        tools.some((row) => /명령 실행 · (거절됨|실패)/.test(row)),
        tools.join(" | "),
    );
    assert.ok(!tools.some((row) => /실행 결과로 저장됨/.test(row)), "no output was stored");
    assert.doesNotMatch(fake.requests.join("\n"), /BULK-LOG-/, "the command never produced output");
});

it("cancelling an approved command keeps the question and tool history without an approval panel", async () => {
    const { page, fake } = e2e;
    fake.script([{ tool: "run_command", args: { command: "node slow.js" } }, { hold: true }]);
    const question = "slow.js 를 실행하고 기다려 주세요";
    await ask(page, question);
    await page.getByTestId("approval-meta").waitFor();
    await decideApproval(page, "approve");
    await page.getByText(/명령 실행 · 실행 중/).waitFor();
    await page.getByTestId("run-cancel").click();
    await waitRunStatus(page, "취소됨");
    const chat = await page.locator("#screen-chat").innerText();
    assert.match(chat, new RegExp(question), "the cancelled run still shows its own question (UI23-09)");
    assert.match(
        (await (await openCurrentToolActivity(page)).getByTestId("tool-row").allInnerTexts()).join(" "),
        /명령 실행/,
    );
    assert.equal(await page.getByTestId("screen-approval").count(), 0, "there is no stale decision prompt");
});

it("an SSE drop is shown as a disconnection, not a cancel, and the run is followed again", async () => {
    const { page, fake } = e2e;
    let dropped = 0;
    await page.route("**/api/v1/runs/*/events", async (route) => {
        if (dropped < 2) {
            dropped += 1;
            await route.abort("connectionreset");
            return;
        }
        await route.continue();
    });
    fake.script([{ text: "재연결 뒤에도 같은 실행의 답입니다." }]);
    await ask(page, "연결이 끊겨도 답해 주세요");
    await page.getByText("연결이 끊겼습니다", { exact: true }).waitFor();
    await waitRunStatus(page, "완료");
    await page.unroute("**/api/v1/runs/*/events");
    assert.match(await page.getByTestId("answer").last().innerText(), /재연결 뒤에도 같은 실행의 답입니다/);
    assert.equal(
        await page.getByText("연결이 끊겼습니다", { exact: true }).count(),
        0,
        "the warning clears after reconnection",
    );
    assert.equal(dropped, 2);
});

it("a source edited after indexing shows SOURCE_CHANGED and a stale index", async () => {
    const { page, files } = e2e;
    await page.getByLabel("심볼·파일 검색어").fill("invoice total tax");
    await page.getByRole("button", { name: "원문 심볼 검색" }).click();
    await page.getByText(/compute_invoice_total · billing\.py:1-4/).waitFor();
    appendFileSync(files.billingPath, "\n\ndef late_fee(days):\n    return days * 5\n");
    await page.getByRole("button", { name: "선택한 원문 묶음 읽기" }).click();
    await page.getByText("SOURCE_CHANGED · 색인 또는 원본이 변경됨").waitFor();
    await page.getByText(/revision \d+ · stale/).waitFor();
    assert.match(await contextPanelText(page), /색인이 오래되었습니다/);
});

it("a PDF without a text layer is reported as unsupported, not as a page in progress", async () => {
    const { page, files } = e2e;
    await registerSource(page, files.scanPdfPath, "scan.pdf");
    await selectPointer(page, "scan.pdf");
    await page.getByRole("button", { name: "PDF parse job 시작" }).click();
    await page.getByText("지원하지 않는 PDF").waitFor({ timeout: 60000 });
    const panel = await contextPanelText(page);
    assert.match(panel, /OCR과 암호 해제는 수행하지 않습니다/);
    assert.doesNotMatch(panel, /페이지 정보를 확인하는 중/);
});
