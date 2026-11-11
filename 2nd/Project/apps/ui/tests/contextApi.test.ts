import assert from "node:assert/strict";
import { test } from "node:test";
import type {
    ContextPreviewRequest,
    PointerDeleteRequest,
    PointerReadRequest,
    SourceMutationRequest,
} from "@securecode/contracts";
import { ApiClientError } from "../src/api/apiErrors.js";
import { ApiHttpClient } from "../src/api/httpClient.js";
import sourceMutationFixture from "../../../contracts/fixtures/pointers/source-register-completed.valid.json";
import pointerListFixture from "../../../contracts/fixtures/pointers/pointer-list.valid.json";
import pointerReadFixture from "../../../contracts/fixtures/pointers/read-result-truncated.valid.json";
import pointerSearchFixture from "../../../contracts/fixtures/pointers/search-result.valid.json";
import pointerDeleteFixture from "../../../contracts/fixtures/pointers/source-unregistered.valid.json";
import contextSearchFixture from "../../../contracts/fixtures/context/preview-search-response.valid.json";
import pdfQueuedFixture from "../../../contracts/fixtures/pointers/pdf-job-queued.valid.json";
import pdfReadyFixture from "../../../contracts/fixtures/pointers/pdf-job-ready.valid.json";

const workspaceId = "ws_00000001";
const sessionId = "ses_00000001";
const sourcePointer = "securecode://source/ws_00000001/src_01?v=2";

test("live context client validates routes and sends only the explicitly selected external path", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const client = new ApiHttpClient("/api/v1", async (input, init) => {
        const url = input instanceof Request ? input.url : input instanceof URL ? input.href : input;
        const requestInit = init ?? {};
        calls.push({ url, init: requestInit });
        const path = new URL(url, "http://localhost").pathname;
        const payload = path.endsWith("/sources")
            ? sourceMutationFixture.data
            : path.endsWith("/context/preview")
              ? contextSearchFixture.data
              : path.endsWith("/pointers/read")
                ? pointerReadFixture.data
                : path.endsWith("/pointers/search")
                  ? pointerSearchFixture.data
                  : requestInit.method === "DELETE"
                    ? pointerDeleteFixture.data
                    : path.endsWith("/pdf/parse")
                      ? pdfQueuedFixture.data
                      : path.endsWith("/pdf/jobs/pdf_00000001")
                        ? pdfReadyFixture.data
                        : pointerListFixture.data;
        return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
    });

    const registerRequest: SourceMutationRequest = {
        schema_version: "1",
        idempotency_key: "register-ui-0001",
        operation: "register",
        target: { location: "external", kind: "file", path: "/tmp/explicit-note.pdf" },
    };
    await client.registerSource(workspaceId, registerRequest);
    const registration = calls[0];
    assert.ok(registration);
    assert.equal(registration.url, `/api/v1/workspaces/${workspaceId}/sources`);
    assert.equal(registration.init.credentials, "same-origin");
    const registrationBody = JSON.parse(readRequestBody(registration.init)) as Record<string, unknown>;
    assert.deepEqual(registrationBody, registerRequest);
    assert.equal("content" in registrationBody, false, "the browser sends no file content");

    await client.listPointers(workspaceId, { kind: "runtime", session_id: sessionId, limit: 20, cursor: "next-page" });
    const listUrl = new URL(calls[1]?.url ?? "", "http://localhost");
    assert.equal(listUrl.pathname, `/api/v1/workspaces/${workspaceId}/pointers`);
    assert.equal(listUrl.searchParams.get("kind"), "runtime");
    assert.equal(listUrl.searchParams.get("session_id"), sessionId);
    assert.equal(listUrl.searchParams.get("cursor"), "next-page");

    const readRequest: PointerReadRequest = {
        schema_version: "1",
        pointer: sourcePointer,
        selector: { type: "line", start: 4, end: 6 },
        max_bytes: 4096,
    };
    await client.readPointer(readRequest);
    const sentRead = JSON.parse(readRequestBody(calls[2]?.init)) as PointerReadRequest;
    assert.deepEqual(sentRead, readRequest);

    await client.searchPointer({
        schema_version: "1",
        pointer: sourcePointer,
        query: "needle",
        limit: 20,
        max_bytes: 8192,
    });
    const previewRequest: ContextPreviewRequest = {
        operation: "search",
        input: { workspace_id: workspaceId, query: "apply_discount", index_revision: 3 },
    };
    await client.previewContext(previewRequest);
    const sentPreview = JSON.parse(readRequestBody(calls[4]?.init)) as ContextPreviewRequest;
    assert.deepEqual(sentPreview, previewRequest);

    const deletion: PointerDeleteRequest = {
        schema_version: "1",
        idempotency_key: "delete-ui-0001",
        kind: "source",
        pointer: sourcePointer,
        workspace_id: workspaceId,
    };
    await client.deletePointer(deletion);
    assert.equal(calls[5]?.init.method, "DELETE");
    assert.deepEqual(JSON.parse(readRequestBody(calls[5]?.init)), deletion);

    await client.parsePdf({
        schema_version: "1",
        workspace_id: workspaceId,
        pointer: "securecode://source/ws_00000001/src_pdf_01?v=2",
        idempotency_key: "parse-pdf-ui-0001",
    });

    function readRequestBody(init: RequestInit | undefined): string {
        if (typeof init?.body !== "string") {
            throw new Error("Expected the UI API client to send a JSON string body.");
        }
        return init.body;
    }
    const job = await client.getPdfJob("pdf_00000001");
    assert.equal(job.state, "ready");
    assert.equal(job.state === "ready" ? job.page_count : 0, 3);
    assert.equal(calls[6]?.url, "/api/v1/pdf/parse");
    assert.equal(calls[7]?.url, "/api/v1/pdf/jobs/pdf_00000001");
});

test("live API preserves safe machine-readable pointer failure details", async () => {
    const errorResponse = {
        schema_version: "1",
        error: {
            code: "NOT_FOUND",
            message: "포인터가 삭제되었습니다.",
            retryable: false,
            request_id: "req_01J9Z6Q4TEST",
            details: { reason: "deleted" },
        },
    };
    const client = new ApiHttpClient(
        "/api/v1",
        async () =>
            new Response(JSON.stringify(errorResponse), {
                status: 404,
                headers: { "content-type": "application/json" },
            }),
    );

    await assert.rejects(client.readPointer({ schema_version: "1", pointer: sourcePointer }), (error: unknown) => {
        assert.ok(error instanceof ApiClientError);
        assert.equal(error.code, "NOT_FOUND");
        assert.equal(error.details?.reason, "deleted");
        return true;
    });
});
