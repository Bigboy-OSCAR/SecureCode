/**
 * 3.6 end to end on the installed SDK with the real context-service (test token counter) and a scripted
 * provider: workspace → R0 index → PDF Source + parse → run (R0 context inserted once by context.select)
 * → approved command whose 2 MB log becomes a Runtime Pointer → partial runtime read → PDF page 2 read
 * → answer. Every captured provider payload and the SDK transcript must hold the selected evidence
 * only: no unrelated sentinel of 1,000 files, no bulk log, no unselected PDF page.
 */
import { probeHomeDir } from "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { it } from "node:test";
import type { RunSnapshot } from "@securecode/contracts";
import { createRun, createSession, isFinished } from "../support/sdkScenario.js";
import { POINTER_PLACEHOLDER, scanFiles, startRuntimeHost, type RuntimeHost } from "../support/runtimeHost.js";

const FIXTURE_PDF = resolve(import.meta.dirname, "../../../../tests/fixtures/pdf/korean-3-pages.pdf");
const INVOICE = [
    "def compute_invoice_total(items, tax_rate):",
    '    """INVOICE-EVIDENCE: sum of line totals plus tax."""',
    "    subtotal = sum(item.price * item.quantity for item in items)",
    "    return round(subtotal * (1 + tax_rate), 2)",
    "",
].join("\n");
const GENERATOR = `
const lines = [];
for (let i = 1; i <= 40000; i++) lines.push(i === 31337 ? "LOG-TARGET total=42" : "BULK-LOG-" + i + "-" + "z".repeat(40));
process.stdout.write(lines.join("\\n") + "\\n");
`;

const toolUse = (id: string, name: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName: name, input }],
});

async function poll<T>(read: () => Promise<T>, done: (value: T) => boolean): Promise<T> {
    let value = await read();
    for (let attempt = 0; attempt < 300 && !done(value); attempt += 1) {
        await new Promise((resolveWait) => setTimeout(resolveWait, 100));
        value = await read();
    }
    return value;
}

async function prepare(host: RuntimeHost): Promise<string> {
    const root = host.workspaceRoot;
    mkdirSync(join(root, "noise"));
    for (let i = 0; i < 1000; i += 1) {
        const id = String(i).padStart(4, "0");
        writeFileSync(
            join(root, "noise", `module_${id}.py`),
            `def helper_${id}():\n    return "UNRELATED-SENTINEL-${id}"\n`,
        );
    }
    writeFileSync(join(root, "billing.py"), INVOICE);
    writeFileSync(join(root, "gen.js"), GENERATOR);
    copyFileSync(FIXTURE_PDF, join(root, "manual.pdf"));
    const ws = host.workspaceId;
    const started = await host.client.send("POST", `/api/v1/workspaces/${ws}/index`, { idempotency_key: "index-0001" });
    assert.equal(started.status, 202, JSON.stringify(started.body));
    const index = await poll(
        () => host.client.send("GET", `/api/v1/workspaces/${ws}/index`),
        (response) => ["ready", "partial"].includes((response.body as { index_status: string }).index_status),
    );
    assert.equal((index.body as { searchable: boolean }).searchable, true, JSON.stringify(index.body));
    const registered = await host.client.send("POST", `/api/v1/workspaces/${ws}/sources`, {
        schema_version: "1",
        idempotency_key: "register-pdf-01",
        operation: "register",
        target: { location: "workspace", kind: "file", path: "manual.pdf" },
    });
    assert.equal(registered.status, 200, JSON.stringify(registered.body));
    const pointer = (registered.body as { items: { pointer: string }[] }).items[0]?.pointer ?? "";
    const parsed = await host.client.send("POST", "/api/v1/pdf/parse", {
        schema_version: "1",
        workspace_id: ws,
        pointer,
        idempotency_key: "parse-pdf-0001",
    });
    const jobId = (parsed.body as { job_id: string }).job_id;
    const job = await poll(
        () => host.client.send("GET", `/api/v1/pdf/jobs/${jobId}`),
        (response) => !["queued", "running"].includes((response.body as { state: string }).state),
    );
    assert.equal((job.body as { state: string }).state, "ready", JSON.stringify(job.body));
    return pointer;
}

async function approveAll(host: RuntimeHost, runId: string): Promise<RunSnapshot> {
    for (;;) {
        const snapshot = await host.client.waitFor(runId, (s) => s.pending_approvals.length > 0 || isFinished(s));
        const approval = snapshot.pending_approvals[0];
        if (!approval) return snapshot;
        await host.client.send("POST", `/api/v1/runs/${runId}/approvals/${approval.approval_id}`, {
            decision: "approve",
            input_digest: approval.input_digest,
        });
    }
}

it("sends only selected evidence to the model across R0, Runtime and PDF pointers", async () => {
    const pdfRead = toolUse("toolu_pdf", "pdf_read_pages", { pointer: "", start_page: 2 });
    const host = await startRuntimeHost([
        toolUse("toolu_cmd", "run_command", { command: "node gen.js" }),
        toolUse("toolu_log", "runtime_read", {
            pointer: POINTER_PLACEHOLDER,
            selector: { type: "line", start: 31337, end: 31337 },
        }),
        pdfRead,
        { text: "합계는 42이며 compute_invoice_total(billing.py)과 manual.pdf p.2를 근거로 합니다." },
        { text: "두 번째 답" },
    ]);
    try {
        const pdfPointer = await prepare(host);
        (pdfRead.toolUses[0] as { input: Record<string, unknown> }).input.pointer = pdfPointer;
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "compute_invoice_total invoice total tax 를 설명해 주세요");
        const done = await approveAll(host, run.run_id);
        assert.equal(done.status, "completed", JSON.stringify(done.terminal));

        const bodies = host.provider.capturedRequests.map((request) => request.bodyText);
        const all = bodies.join("\n");
        const firstUser = (JSON.parse(bodies[0] ?? "{}") as { messages: { content: { text?: string }[] }[] })
            .messages[0];
        const firstText = firstUser?.content.map((part) => part.text ?? "").join("") ?? "";
        assert.match(
            firstText,
            /<securecode-context id="cand_[^"]+" source="billing\.py">/,
            "R0 bundle in the first request",
        );
        assert.match(bodies[0] ?? "", /INVOICE-EVIDENCE/);
        assert.doesNotMatch(all, /UNRELATED-SENTINEL/, "no unrelated file of the 1,000 reached the model");
        assert.match(all, /LOG-TARGET total=42/, "the selected log line was read");
        // Only the descriptor's 512-byte preview (log lines 1-10) is shown; the other ~40,000 lines stay stored.
        assert.doesNotMatch(all, /BULK-LOG-\d{3,}-/, "the bulk log stayed in the Runtime store");
        assert.match(all, /stored_bytes: \d{7}/, "the command output was stored as a pointer");
        assert.match(all, /PAGE-TWO-SENTINEL/, "the selected PDF page was read");
        assert.doesNotMatch(all, /PAGE-ONE-SENTINEL|PAGE-THREE-SENTINEL/, "unselected PDF pages stayed out");

        const second = await createRun(
            host,
            sessionId,
            "compute_invoice_total invoice total tax 를 다시 요약해 주세요",
        );
        const again = await host.client.waitFor(second.run_id, isFinished);
        assert.equal(again.status, "completed", JSON.stringify(again.terminal));
        const lastRequest = host.provider.capturedRequests.at(-1)?.bodyText ?? "";
        assert.equal(
            lastRequest.split("INVOICE-EVIDENCE").length - 1,
            1,
            "the R0 fragment is in history once, not re-inserted",
        );

        const secondRun = host.provider.capturedRequests
            .slice(bodies.length)
            .map((request) => request.bodyText)
            .join("\n");
        assert.doesNotMatch(
            secondRun,
            /BULK-LOG-\d{3,}-|UNRELATED-SENTINEL|PAGE-(ONE|THREE)-SENTINEL/,
            "no re-insertion",
        );
        for (const stored of [scanFiles(probeHomeDir), scanFiles(host.dataDir)]) {
            assert.doesNotMatch(stored, /UNRELATED-SENTINEL|BULK-LOG-\d{3,}-/, "canonical transcript and host state");
            assert.doesNotMatch(stored, /PAGE-ONE-SENTINEL|PAGE-THREE-SENTINEL/);
        }
    } finally {
        await host.close();
    }
});
