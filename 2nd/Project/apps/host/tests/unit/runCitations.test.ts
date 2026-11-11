import assert from "node:assert/strict";
import { test } from "node:test";
import type { AnswerCitation, SymbolLocation } from "@securecode/contracts";
import { RunEventLog } from "../../src/routes/runs/eventLog.js";
import { RunRecorder } from "../../src/routes/runs/runRecorder.js";
import { toSnapshot, type RunRecord } from "../../src/routes/runs/runRecord.js";

const locations: SymbolLocation[] = ["billing.py", "helpers.py", "constants.py"].map((path, index) => ({
    symbol_id: `sym_0000000${index}`,
    qualname: `symbol${index}`,
    kind: "function",
    relative_path: path,
    start_line: 1,
    end_line: 2,
    content_sha256: String(index).repeat(64),
}));
const ref = { kind: "symbol" as const, candidate_id: "cand_00000000", index_revision: 1 };
function record(): RunRecord {
    return {
        run_id: "run_00000000",
        session_id: "ses_00000000",
        workspace_id: "ws_00000000",
        status: "running",
        created_at: "2026-11-11T00:00:00Z",
        updated_at: "2026-11-11T00:00:00Z",
        prompt_preview: "question",
        answer_text: "",
        answer_truncated: false,
        tool_calls: [],
        tool_calls_truncated: false,
        pending_approvals: [],
        approval_history: [],
        terminal: null,
        last_sequence: 0,
        citations: [],
    };
}
const replay = { oldest_sequence: 1, last_sequence: 1, terminal: false };

test("one bundle retains each symbol citation while repeat citations are deduplicated", () => {
    const state = record();
    const recorder = new RunRecorder(
        state,
        new RunEventLog(state, () => 0),
        () => {},
        () => 0,
    );
    for (const location of [...locations, ...locations]) recorder.cite({ ref, location });
    assert.equal(state.citations?.length, 3);
    assert.deepEqual(
        toSnapshot(state, replay).answer.citations?.map((item) =>
            "location" in item ? item.location.relative_path : null,
        ),
        ["billing.py", "helpers.py", "constants.py"],
    );
});

test("older stored bundle metadata restores all related locations without doubling new expanded citations", () => {
    const state = record();
    const primary = locations[0];
    assert.ok(primary);
    const citation: AnswerCitation = { ref, location: primary, related_locations: locations.slice(1) };
    state.citations = [citation];
    assert.equal(toSnapshot(state, replay).answer.citations?.length, 3);
    state.citations.push(...locations.map((location) => ({ ref, location })));
    assert.equal(toSnapshot(state, replay).answer.citations?.length, 3);
});
