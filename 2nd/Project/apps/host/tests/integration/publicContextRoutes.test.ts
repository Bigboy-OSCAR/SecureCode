/**
 * 3.6 public routes on the real context-service (test token counter): Source register/read/search/list/
 * delete, R0 index and preview search/bundle, preview plan → run with the confirmed range and digest,
 * stale preview and unusable explicit choices refused before any model call. Responses are validated
 * against the contracts; these are the UI integration examples recorded in the 3.6 handoff.
 */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { it } from "node:test";
import { SCHEMA_REFS } from "@securecode/contracts";
import { validator } from "../support/hostHarness.js";
import { createSession, isFinished } from "../support/sdkScenario.js";
import { startRuntimeHost, type RuntimeHost } from "../support/runtimeHost.js";

const APP = "def apply_discount(price, rate):\n    return price * (1 - rate)  # DISCOUNT-EVIDENCE\n";

function valid(ref: string, body: unknown): void {
    const result = validator.validate(ref, body);
    assert.ok(result.valid, `${ref}: ${result.errors.join("; ")}`);
}

async function indexReady(host: RuntimeHost): Promise<number> {
    await host.client.send("POST", `/api/v1/workspaces/${host.workspaceId}/index`, { idempotency_key: "index-0001" });
    for (let attempt = 0; attempt < 300; attempt += 1) {
        const status = await host.client.send("GET", `/api/v1/workspaces/${host.workspaceId}/index`);
        valid(SCHEMA_REFS.indexStatusResponse, status.body);
        const body = status.body as { index_status: string; index_revision: number | null };
        if (["ready", "partial"].includes(body.index_status)) return body.index_revision ?? 1;
        await new Promise((done) => setTimeout(done, 100));
    }
    throw new Error("index did not become ready");
}

it("serves Source, preview and run creation routes with confirmed ranges and digests", async () => {
    const host = await startRuntimeHost([{ text: "할인은 DISCOUNT-EVIDENCE 줄에 있습니다 (app.py)." }]);
    try {
        writeFileSync(join(host.workspaceRoot, "app.py"), APP);
        const ws = host.workspaceId;
        const revision = await indexReady(host);

        const registered = await host.client.send("POST", `/api/v1/workspaces/${ws}/sources`, {
            schema_version: "1",
            idempotency_key: "register-app-1",
            operation: "register",
            target: { location: "workspace", kind: "file", path: "app.py" },
        });
        valid(SCHEMA_REFS.sourceMutationResult, registered.body);
        const pointer = (registered.body as { items: { pointer: string }[] }).items[0]?.pointer ?? "";

        const read = await host.client.send("POST", "/api/v1/pointers/read", {
            schema_version: "1",
            pointer,
            selector: { type: "line", start: 2, end: 2 },
            max_bytes: 4096,
        });
        valid(SCHEMA_REFS.pointerReadResult, read.body);
        const selection = (read.body as { provenance: { selection: unknown } }).provenance.selection;
        const found = await host.client.send("POST", "/api/v1/pointers/search", {
            schema_version: "1",
            pointer,
            query: "DISCOUNT",
        });
        valid(SCHEMA_REFS.pointerSearchResult, found.body);
        const listed = await host.client.send("GET", `/api/v1/workspaces/${ws}/pointers?kind=source`);
        valid(SCHEMA_REFS.pointerListResult, listed.body);

        const search = await host.client.send("POST", "/api/v1/context/preview", {
            operation: "search",
            input: { workspace_id: ws, query: "apply_discount", index_revision: revision },
        });
        valid(SCHEMA_REFS.contextPreviewResponse, search.body);
        const candidate = (search.body as { result: { candidates: { candidate_id: string }[] } }).result.candidates[0];
        assert.ok(candidate, "R0 found the function");
        const bundle = await host.client.send("POST", "/api/v1/context/preview", {
            operation: "bundle",
            input: {
                workspace_id: ws,
                candidate_id: candidate.candidate_id,
                index_revision: revision,
                max_tokens: 2000,
            },
        });
        valid(SCHEMA_REFS.contextPreviewResponse, bundle.body);

        const sessionId = await createSession(host);
        const refs = [{ kind: "source", pointer, selection }];
        const input = {
            workspace_id: ws,
            session_id: sessionId,
            index_revision: revision,
            prompt: "할인 계산은?",
            context_refs: refs,
        };
        const plan = await host.client.send("POST", "/api/v1/context/preview", { operation: "plan", input });
        valid(SCHEMA_REFS.contextPreviewResponse, plan.body);
        const digest = (plan.body as { result: { preview_digest: string } }).result.preview_digest;

        const stale = await host.client.send("POST", `/api/v1/sessions/${sessionId}/runs`, {
            prompt: "할인 계산은?",
            idempotency_key: "run-stale-0001",
            context_refs: refs,
            preview_digest: "f".repeat(64),
        });
        assert.equal(stale.status, 422);
        assert.equal((stale.body as { error: { details: { reason: string } } }).error.details.reason, "stale_preview");

        const wrong = [
            { kind: "source", pointer, selection: { ...(selection as object), content_sha256: "0".repeat(64) } },
        ];
        const refused = await host.client.send("POST", `/api/v1/sessions/${sessionId}/runs`, {
            prompt: "할인 계산은?",
            idempotency_key: "run-wrong-0001",
            context_refs: wrong,
        });
        assert.equal((refused.body as { error: { code: string } }).error.code, "SOURCE_CHANGED");
        assert.equal(host.provider.capturedRequests.length, 0, "refused runs never call the model");

        const run = await host.client.send("POST", `/api/v1/sessions/${sessionId}/runs`, {
            prompt: "할인 계산은?",
            idempotency_key: "run-good-0001",
            context_refs: refs,
            preview_digest: digest,
        });
        assert.equal(run.status, 201, JSON.stringify(run.body));
        const done = await host.client.waitFor((run.body as { run_id: string }).run_id, isFinished);
        assert.equal(done.status, "completed");
        const first = host.provider.capturedRequests[0]?.bodyText ?? "";
        assert.match(first, /DISCOUNT-EVIDENCE/, "the confirmed range was inserted");
        assert.doesNotMatch(
            first,
            /def apply_discount\(price, rate\):\\n {4}return/,
            "only line 2, not the whole file twice",
        );

        const removed = await host.client.send("DELETE", "/api/v1/pointers", {
            schema_version: "1",
            idempotency_key: "delete-app-01",
            kind: "source",
            pointer,
            workspace_id: ws,
        });
        valid(SCHEMA_REFS.pointerDeleteResult, removed.body);
    } finally {
        await host.close();
    }
});
