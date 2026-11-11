import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fixtureAdapter } from "./support/fixtureAdapter.js";
import { PointerReadFailureNotice } from "../src/features/pointers/components/LivePointerReadPanel.js";
import { PdfJobDetails } from "../src/features/pointers/components/LivePdfPanel.js";

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
