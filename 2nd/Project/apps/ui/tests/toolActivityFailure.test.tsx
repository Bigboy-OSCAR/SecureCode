/** A stale-index stop must remain actionable even while its tool details are collapsed. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { RunSnapshot } from "@securecode/contracts";
import { ToolHistory } from "../src/features/chat/components/ToolHistory.js";
import { fixtureAdapter } from "./support/fixtureAdapter.js";

test("a stale-index failure shows recovery outside collapsed activity without changing ordinary cancellation", () => {
    const base = fixtureAdapter.runs.find((run) => run.status === "completed");
    assert.ok(base);
    const failed: RunSnapshot = {
        ...base,
        status: "failed",
        terminal: {
            status: "failed",
            finished_at: base.updated_at,
            reason_code: "SOURCE_CHANGED",
            message: "인덱스 생성·갱신에서 해당 프로젝트를 갱신한 뒤 다시 질문하세요.",
        },
        tool_calls: [{ tool_call_id: "stale", tool_name: "code_read", phase: "failed", summary: "code_read failed" }],
    };
    const markup = renderToStaticMarkup(createElement(ToolHistory, { run: failed }));
    assert.doesNotMatch(markup, /<details[^>]* open/);
    assert.ok(markup.indexOf("인덱스 갱신이 필요합니다") > markup.lastIndexOf("</details>"));
    assert.match(markup, /해당 프로젝트를 갱신한 뒤 다시 질문하세요/);
    const cancelled = renderToStaticMarkup(
        createElement(ToolHistory, {
            run: {
                ...failed,
                status: "cancelled",
                terminal: { status: "cancelled", finished_at: base.updated_at, message: "the run was cancelled" },
            },
        }),
    );
    assert.doesNotMatch(cancelled, /alert-warning|the run was cancelled/);
});
