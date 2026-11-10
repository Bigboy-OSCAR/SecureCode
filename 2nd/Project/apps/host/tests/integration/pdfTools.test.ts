/**
 * 4.9 host PDF tools against the real context-service (test token counter, registered workspace root):
 * pdf_parse/pdf_status return job metadata only, pdf_read_pages returns just the requested page with its
 * citation, pdf_search cites pages, and errors surface as coded tool errors instead of text.
 */
import assert from "node:assert/strict";
import { copyFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { after, before, it } from "node:test";
import { pdfTools } from "../../src/cline/tools/pdfTools.js";
import { createPdfClient } from "../../src/context-client/pdfClient.js";
import { validator } from "../support/hostHarness.js";
import { startCountedService, type CountedService } from "../support/runtimeHost.js";

const WORKSPACE = "ws_00000001";
const FIXTURE = resolve(import.meta.dirname, "../../../../tests/fixtures/pdf/korean-3-pages.pdf");
let service: CountedService;
let pointer = "";

function run(name: string, input: Record<string, unknown>): Promise<string> {
    const client = createPdfClient({ baseUrl: service.url, internalToken: service.token, validator });
    const tool = pdfTools({ service: client, workspaceId: WORKSPACE, timeoutMs: 20000 }).find(
        (entry) => entry.tool.name === name,
    );
    assert.ok(tool);
    return tool.tool.execute(input, { signal: AbortSignal.timeout(30000) } as never) as Promise<string>;
}

before(async () => {
    const root = mkdtempSync(join(tmpdir(), "securecode-pdf-ws-"));
    copyFileSync(FIXTURE, join(root, "report.pdf"));
    service = await startCountedService({ SECURECODE_TEST_WORKSPACE_ROOTS: JSON.stringify({ [WORKSPACE]: root }) });
    const response = await fetch(`${service.url}/internal/v1/source/register`, {
        method: "POST",
        headers: { authorization: `Bearer ${service.token}`, "content-type": "application/json" },
        body: JSON.stringify({
            schema_version: "1",
            workspace_id: WORKSPACE,
            idempotency_key: "register-pdf-1",
            operation: "register",
            target: { location: "workspace", kind: "file", path: "report.pdf" },
        }),
    });
    pointer = ((await response.json()) as { items: { pointer: string }[] }).items[0]?.pointer ?? "";
});

after(async () => {
    await service.stop();
});

it("parses to job metadata only and reads exactly the requested page with its citation", async () => {
    let status = JSON.parse(await run("pdf_parse", { pointer })) as Record<string, unknown>;
    for (let attempt = 0; attempt < 300 && (status.state === "queued" || status.state === "running"); attempt += 1) {
        await new Promise((done) => setTimeout(done, 100));
        status = JSON.parse(await run("pdf_status", { job_id: status.job_id })) as Record<string, unknown>;
    }
    assert.equal(status.state, "ready");
    assert.equal(status.page_count, 3);
    assert.deepEqual(Object.keys(status).sort(), ["job_id", "page_count", "state"]);

    const page = JSON.parse(await run("pdf_read_pages", { pointer, start_page: 2 })) as {
        page: number;
        content: string;
        range: { type: string; page: number; start: number; end: number };
    };
    assert.equal(page.page, 2);
    assert.match(page.content, /PAGE-TWO-SENTINEL/);
    assert.match(page.content, /둘째 페이지/);
    assert.doesNotMatch(page.content, /PAGE-ONE|PAGE-THREE/);
    assert.equal(page.range.end - page.range.start, Buffer.byteLength(page.content, "utf8"));

    const found = JSON.parse(await run("pdf_search", { pointer, query: "바다" })) as {
        matches: { page: number }[];
    };
    assert.deepEqual(
        found.matches.map((match) => match.page),
        [2],
    );
});

it("reports a missing page as a coded tool error", async () => {
    await assert.rejects(run("pdf_read_pages", { pointer, start_page: 9 }), /INVALID_SELECTOR \(page_out_of_range\)/);
});
