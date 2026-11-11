/**
 * 1.6 acceptance regressions for the 2.3 review requests (UI23-04/05/06/08): tool phases and unknown sizes,
 * answers that are never cut silently, server-verified citations, approval metadata and the narrow-layout
 * panel switcher.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ExplicitContextRef, RunCreateRequest, RunSnapshot, SessionId } from "@securecode/contracts";
import { fixtureAdapter } from "./support/fixtureAdapter.js";
import { FixtureRunClient } from "./support/fixtureRunClient.js";
import { PanelSwitcher, panelClass } from "../src/app/PanelSwitcher.js";
import { ApprovalCard } from "../src/features/approvals/components/ApprovalCard.js";
import { ANSWER_STEP_CHARS, AnswerView } from "../src/features/chat/components/AnswerView.js";
import { AnswerText } from "../src/features/chat/components/AnswerText.js";
import { ToolHistory } from "../src/features/chat/components/ToolHistory.js";
import { RunController } from "../src/features/chat/model/runController.js";
import { outputLabel, phaseLabel, toolLabel } from "../src/features/chat/model/toolLabels.js";

function render(element: ReactNode): string {
    return renderToStaticMarkup(createElement("div", null, element));
}

function completedRun(): RunSnapshot {
    const run = fixtureAdapter.runs.find((candidate) => candidate.status === "completed");
    assert.ok(run, "a completed run fixture exists");
    return run;
}

test("tool history shows each phase and never turns a missing size into 0 bytes", () => {
    const markup = render(
        createElement(ToolHistory, {
            tools: [
                { tool_call_id: "t1", tool_name: "run_command", phase: "awaiting_approval", summary: "node gen.js" },
                {
                    tool_call_id: "t2",
                    tool_name: "run_command",
                    phase: "completed",
                    summary: "done",
                    output_bytes: 908895,
                    output_pointer:
                        "securecode://runtime/ws_00000001/ses_00000001/00000000-0000-4000-8000-000000000000?v=1",
                },
                { tool_call_id: "t3", tool_name: "pdf_read_pages", phase: "rejected", summary: "page 2" },
            ],
            truncated: false,
        }),
    );
    assert.ok(markup.includes("명령 실행 · 승인 대기"));
    assert.ok(markup.includes("PDF 페이지 읽기 · 거절됨"));
    assert.ok(markup.includes("크기 미확인"));
    assert.ok(markup.includes("908,895 bytes · 실행 결과로 저장됨"));
    assert.equal(markup.includes("0 bytes"), false);
    assert.equal(markup.includes("securecode://"), false, "pointer URIs stay out of the DOM");
    assert.equal(toolLabel("unknown_tool"), "unknown_tool");
    assert.equal(phaseLabel("cancelled"), "취소됨");
    assert.equal(
        outputLabel({ tool_call_id: "x", tool_name: "read_file", phase: "running", summary: "s" }),
        "크기 미확인",
    );
});

test("a long answer is shown in steps with the remaining length, not cut silently", () => {
    const text = "가".repeat(ANSWER_STEP_CHARS + 1234);
    const markup = render(
        createElement(AnswerView, { run: { ...completedRun(), answer: { text, truncated: false } } }),
    );
    assert.ok(markup.includes("답변 더 보기 (1,234자 남음)"));
    assert.equal(markup.includes("…"), false);
    assert.equal(markup.includes("aria-live"), false, "the streamed answer is not a live region");
});

test("citations come only from the server: verified sources are listed, none is said plainly", () => {
    const base = completedRun();
    const cited = render(
        createElement(AnswerView, {
            run: {
                ...base,
                answer: {
                    text: "합계는 42",
                    truncated: false,
                    citations: [
                        {
                            ref: {
                                kind: "symbol",
                                candidate_id: "cand_3ca867b85ea162c9f1ccd12621167335824ec6d1",
                                index_revision: 1,
                            },
                            location: {
                                symbol_id: "sym_3ca867b85ea162c9f1ccd12621167335824ec6d1",
                                qualname: "compute_invoice_total",
                                kind: "function",
                                relative_path: "billing.py",
                                start_line: 1,
                                end_line: 4,
                                content_sha256: "d43cbb38efbec5a88ecfc2f69133d40b6bc78e1da138e7472ed97ded45db30eb",
                            },
                        },
                    ],
                    citations_page: { limit: 50, next_cursor: null, has_more: false },
                },
            },
        }),
    );
    assert.ok(cited.includes("billing.py:1-4 · compute_invoice_total · revision 1"));
    const uncited = render(createElement(AnswerView, { run: { ...base, answer: { text: "답", truncated: false } } }));
    assert.ok(uncited.includes("서버가 확인한 근거가 없습니다"));
});

test("an approval shows kind, tool, targets and expiry before any decision", () => {
    const snapshot = fixtureAdapter.runs.find((run) => run.pending_approvals.length > 0);
    assert.ok(snapshot, "a run fixture with a pending approval exists");
    const controller = new RunController(
        new FixtureRunClient(),
        snapshot.session_id,
        snapshot.workspace_id,
        () => "ui-test-idempotency-key",
        () => Date.parse("2026-11-04T09:01:00Z"),
    );
    controller.restore(snapshot);
    const markup = render(createElement(ApprovalCard, { controller, state: controller.getSnapshot() }));
    for (const label of ["종류", "도구", "대상", "만료", "<time"]) {
        assert.ok(markup.includes(label), `approval metadata "${label}" is shown`);
    }
    assert.ok(markup.includes('id="approval-heading" tabindex="-1"'), "the card heading can take focus back");
    controller.dispose();
});

test("the narrow-layout switcher exposes which panel is expanded", () => {
    const markup = render(createElement(PanelSwitcher, { open: "context", onToggle: () => undefined }));
    assert.ok(markup.includes('aria-controls="context-panel"'));
    assert.ok(markup.includes('aria-expanded="true"'));
    assert.ok(markup.includes("프로젝트 패널 펼치기"));
    assert.equal(panelClass("context-sidebar", "context", "context"), "context-sidebar side-panel side-panel-open");
    assert.equal(panelClass("project-sidebar", "project", "context"), "project-sidebar side-panel");
});

test("answer formatting escapes model HTML and preserves fenced code as text", () => {
    const markup = render(
        createElement(AnswerText, {
            text: "## Result\n<script>alert(1)</script>\n```html\n<img src=x onerror=alert(1)>\n```",
        }),
    );
    assert.ok(markup.includes("<h4>Result</h4>"));
    assert.ok(markup.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
    assert.ok(markup.includes("&lt;img src=x onerror=alert(1)&gt;"));
    assert.equal(markup.includes("<script>"), false);
    assert.equal(markup.includes("<img src=x"), false);
});

test("retrying a lost run response preserves the exact selected context and idempotency key", async () => {
    const requests: RunCreateRequest[] = [];
    class LostResponseClient extends FixtureRunClient {
        override async createRun(sessionId: SessionId, request: RunCreateRequest): Promise<RunSnapshot> {
            requests.push(structuredClone(request));
            const snapshot = await super.createRun(sessionId, request);
            if (requests.length === 1) throw new Error("response lost");
            return snapshot;
        }
    }
    const template = fixtureAdapter.runs[0]!;
    let keyCount = 0;
    const controller = new RunController(
        new LostResponseClient(),
        template.session_id,
        template.workspace_id,
        () => `selected-context-key-${++keyCount}`,
    );
    const refs: ExplicitContextRef[] = [
        {
            kind: "source",
            pointer: "securecode://source/ws_00000001/00000000-0000-4000-8000-000000000000?v=1",
            selection: {
                revision: 1,
                content_sha256: "a".repeat(64),
                range: {
                    type: "pdf_page",
                    page: 2,
                    start: 0,
                    end: 17,
                    parser_version: "test-parser",
                },
            },
        },
    ];
    try {
        assert.equal(await controller.createRun("selected page", refs), false);
        assert.equal(await controller.createRun("selected page", []), false, "changed selection cannot reuse the key");
        assert.equal(requests.length, 1);
        assert.equal(await controller.createRun("selected page", structuredClone(refs)), true);
        assert.equal(keyCount, 1);
        assert.deepEqual(requests[0], requests[1]);
        assert.deepEqual(requests[1]?.context_refs, refs);
    } finally {
        controller.dispose();
    }
});
