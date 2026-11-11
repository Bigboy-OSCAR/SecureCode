/**
 * E2E (fixture provider): new project → index READY → question → R0 evidence → approved command →
 * large log stored as a Runtime Pointer → partial re-read → PDF page via its Source Pointer → answer
 * citations, all through the browser against the real host, SDK and context-service.
 */
import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { runtimePointerIn } from "./support/fakeLlama.js";
import {
    ask,
    buildIndex,
    contextPanelText,
    decideApproval,
    registerProject,
    registerSource,
    selectPointer,
    sourcePointer,
    startSession,
    waitRunStatus,
} from "./support/uiActions.js";

let e2e: E2E;

before(async () => {
    e2e = await startE2E();
});

after(async () => {
    await e2e?.stop();
});

it("answers from R0 evidence, a stored log and a PDF page, and cites only verified inputs", async () => {
    const { page, fake, files } = e2e;
    await registerProject(page, "e2e-project", files.projectDir);
    await buildIndex(page);
    await startSession(page, "e2e-project");
    await registerSource(page, files.pdfPath, "manual.pdf");
    await page.getByRole("button", { name: "PDF parse job 시작" }).click();
    await page.getByText(/ready · 원본 3쪽/).waitFor({ timeout: 60000 });
    const pdfPointer = await sourcePointer(page, "manual.pdf");

    fake.script([
        { tool: "run_command", args: { command: "node gen.js" } },
        {
            tool: "runtime_search",
            args: ({ lastToolResult }) => ({ pointer: runtimePointerIn(lastToolResult), query: "LOG-TARGET" }),
        },
        { tool: "pdf_read_pages", args: { pointer: pdfPointer, start_page: 2 } },
        { text: "합계는 42입니다. 근거: compute_invoice_total(billing.py)과 manual.pdf 2쪽." },
    ]);
    await ask(page, "compute_invoice_total invoice total tax 를 확인하고 gen.js 로그의 total 값을 알려 주세요");
    await page.getByTestId("approval-meta").waitFor();
    assert.match(await page.getByTestId("approval-meta").innerText(), /명령 실행/);
    await decideApproval(page, "approve");
    await waitRunStatus(page, "완료");

    const answer = await page.getByTestId("answer").innerText();
    assert.match(answer, /합계는 42입니다/);
    assert.match(answer, /billing\.py:1-4 · compute_invoice_total · revision 1/, "R0 fragment is cited");
    assert.match(answer, /원본 PDF 2쪽/, "the PDF page read is cited");
    const tools = await page.getByTestId("tool-row").allInnerTexts();
    assert.ok(tools.some((row) => /명령 실행 · 완료/.test(row) && /실행 결과로 저장됨/.test(row)));
    assert.ok(tools.some((row) => /실행 결과 검색 · 완료/.test(row)));
    assert.ok(tools.some((row) => /PDF 페이지 읽기 · 완료/.test(row)));
    assert.equal(await page.getByTestId("question-input").inputValue(), "", "the sent question was cleared");

    const sent = fake.requests.join("\n");
    assert.match(fake.requests[0] ?? "", /def compute_invoice_total/, "R0 evidence reached the first request");
    assert.doesNotMatch(sent, /UNRELATED-SENTINEL/, "unrelated files stayed out of every request");
    assert.match(sent, /LOG-TARGET total=42/, "the searched log line reached the model");
    assert.doesNotMatch(sent, /BULK-LOG-1\d{3,}-/, "the bulk log stayed in the Runtime store");
    assert.match(sent, /PAGE-TWO-SENTINEL/);
    assert.doesNotMatch(sent, /PAGE-ONE-SENTINEL|PAGE-THREE-SENTINEL/, "unselected PDF pages stayed out");

    // The stored log: listed with tool, run and expiry, then re-read in part from the UI.
    await page.getByRole("button", { name: "Runtime 목록 새로고침" }).click();
    const runtimeRow = page.locator("li").filter({ hasText: /^output-/ });
    await runtimeRow.first().waitFor();
    const rowText = await runtimeRow.first().innerText();
    assert.match(rowText, /도구: run_command/);
    assert.match(rowText, /실행: run_[A-Za-z0-9-]+/);
    assert.match(rowText, /만료: /);
    await runtimeRow.first().locator("input[type=radio]").check();
    await page.getByLabel("포인터 내용 검색").fill("LOG-TARGET");
    await page.getByRole("button", { name: "포인터 검색" }).click();
    await page.getByText("줄 13579").waitFor();

    // A large external Source: a bounded line range and a Korean search, never the whole file.
    await registerSource(page, files.bigLogPath, "big.log");
    await selectPointer(page, "big.log");
    await page.getByLabel("시작 줄").fill("25000");
    await page.getByLabel("끝 범위 (선택)").fill("25000");
    await page.getByRole("button", { name: "범위 읽기" }).click();
    await page.getByText("EXT-TARGET 결제 오류 코드 E-7731").first().waitFor();
    await page.getByLabel("포인터 내용 검색").fill("결제 오류");
    await page.getByRole("button", { name: "포인터 검색" }).click();
    await page.getByText(/줄 25000 ·/).waitFor();
    const received = await page.evaluate(() =>
        performance
            .getEntriesByType("resource")
            .filter((entry) => entry.name.includes("/api/v1/"))
            .reduce((total, entry) => total + (entry as PerformanceResourceTiming).decodedBodySize, 0),
    );
    assert.ok(received < 512 * 1024, `the browser received ${received} bytes of API data, not the 2 MB file`);
    const panel = await contextPanelText(page);
    assert.doesNotMatch(panel, /ext line 2\d{4} y/, "no unrequested range of the big file is in the DOM");
});
