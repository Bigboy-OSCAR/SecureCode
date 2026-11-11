import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fixtureAdapter } from "./support/fixtureAdapter.js";
import { PointerReadFailureNotice } from "../src/features/pointers/components/LivePointerReadPanel.js";
import { PdfJobDetails } from "../src/features/pointers/components/LivePdfPanel.js";
import { formatCitation, formatSelection } from "../src/features/shared/model/provenanceLabels.js";

function render(element: ReactNode): string {
    return renderToStaticMarkup(createElement("div", null, element));
}

test("live pointer read distinguishes expired, deleted, changed, no-match, and budget states", () => {
    const cases = [
        {
            code: "EXPIRED",
            reason: null,
            expired: true,
            deleted: false,
            expected: "Runtime Pointer expired",
        },
        {
            code: "NOT_FOUND",
            reason: "deleted",
            expired: false,
            deleted: true,
            expected: "Runtime Pointer deleted",
        },
        {
            code: "SOURCE_CHANGED",
            reason: "stale",
            expired: false,
            deleted: false,
            expected: "원본 변경됨",
        },
        {
            code: "BUDGET_EXCEEDED",
            reason: null,
            expired: false,
            deleted: false,
            expected: "BUDGET_EXCEEDED",
        },
        {
            code: "NO_MATCH",
            reason: null,
            expired: false,
            deleted: false,
            expected: "NO_MATCH",
        },
    ];

    for (const item of cases) {
        const markup = render(
            createElement(PointerReadFailureNotice, {
                error: `failure ${item.code}`,
                code: item.code,
                reason: item.reason,
                expired: item.expired,
                deleted: item.deleted,
            }),
        );
        assert.ok(markup.includes(item.expected), `${item.code} should have a distinct user-visible state.`);
    }
});

test("live PDF view presents job metadata and every terminal service state", () => {
    for (const state of ["queued", "running", "ready", "partial", "unsupported", "failed", "stale"] as const) {
        const job = fixtureAdapter.pdfJobs.find((candidate) => candidate.state === state);
        assert.ok(job, `Expected a validated fixture for ${state}.`);
        const markup = render(createElement(PdfJobDetails, { job }));
        assert.ok(markup.length > 0);
        if (state === "ready") {
            assert.ok(markup.includes("원본 3쪽"));
            assert.ok(markup.includes("parser"));
        } else if (state === "unsupported") {
            assert.ok(markup.includes("지원하지 않는 PDF"));
        } else if (state === "failed") {
            assert.ok(markup.includes("PDF parsing failed"));
        } else if (state === "stale") {
            assert.ok(markup.includes("PDF 원본 또는 parser가 변경됨"));
        } else if (state === "queued" || state === "running") {
            assert.ok(markup.includes(state));
            assert.ok(markup.includes("추출 텍스트는 이 상태 응답에 포함되지 않습니다"));
        }
    }
});

test("context fragments show the server-confirmed source: symbol file and lines, PDF page, byte range", () => {
    const symbol = formatCitation({
        ref: { kind: "symbol", candidate_id: "cand_3ca867b85ea162c9f1ccd12621167335824ec6d1", index_revision: 2 },
        location: {
            symbol_id: "sym_3ca867b85ea162c9f1ccd12621167335824ec6d1",
            qualname: "compute_invoice_total",
            kind: "function",
            relative_path: "billing.py",
            start_line: 1,
            end_line: 4,
            content_sha256: "d43cbb38efbec5a88ecfc2f69133d40b6bc78e1da138e7472ed97ded45db30eb",
        },
    });
    assert.equal(symbol, "billing.py:1-4 · compute_invoice_total · revision 2 · sha256 d43cbb38efbe…");

    const page = formatSelection({ type: "pdf_page", page: 2, start: 0, end: 52, parser_version: "pdf-text-v1" });
    assert.equal(page, "원본 PDF 2쪽 · byte 0-52 · parser pdf-text-v1");
    assert.equal(formatSelection({ type: "byte", start: 10, end: 20 }), "원본 byte 10-20");
});
