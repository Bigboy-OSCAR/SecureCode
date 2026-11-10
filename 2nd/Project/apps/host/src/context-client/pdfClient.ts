/**
 * Host client for the 4.9 PDF service (context-service /internal/v1/pdf/* and Source pdf_page reads).
 * Every response is validated against the contracts and checked against the caller's workspace and
 * pointer; an error envelope becomes a ContextServiceError. No call returns a whole document.
 */
import {
    SCHEMA_REFS,
    type ContractValidator,
    type ErrorResponse,
    type PdfJobStatus,
    type PointerReadResult,
    type PointerSearchResult,
} from "@securecode/contracts";
import { ContextServiceError } from "./contextServiceError.js";
import { requestLoopbackJson } from "./loopbackHttp.js";

export interface PdfPageRead {
    pointer: string;
    startPage: number;
    endPage?: number;
    maxBytes?: number;
    maxTokens?: number;
    cursor?: string;
}

/** PDF operations the app-owned PDF tools use; workspace scope comes from the authenticated session. */
export interface PdfService {
    parse(workspaceId: string, pointer: string, idempotencyKey: string, signal: AbortSignal): Promise<PdfJobStatus>;
    status(workspaceId: string, jobId: string, signal: AbortSignal): Promise<PdfJobStatus>;
    readPages(workspaceId: string, request: PdfPageRead, signal: AbortSignal): Promise<PointerReadResult>;
    search(
        workspaceId: string,
        request: { pointer: string; query: string; limit?: number },
        signal: AbortSignal,
    ): Promise<PointerSearchResult>;
}

export interface PdfClientOptions {
    baseUrl: string;
    internalToken: string;
    validator: ContractValidator;
    timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 15000;

function mismatch(reason: string): ContextServiceError {
    return new ContextServiceError("SERVICE_UNAVAILABLE", "PDF service returned an unexpected result", true, {
        reason,
    });
}

export function createPdfClient(options: PdfClientOptions): PdfService {
    const { validator } = options;

    async function call(path: string, workspaceId: string, payload: object, signal: AbortSignal): Promise<unknown> {
        const timeout = AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
        const response = await requestLoopbackJson(
            options.baseUrl,
            path,
            options.internalToken,
            { schema_version: "1", workspace_id: workspaceId, ...payload },
            AbortSignal.any([signal, timeout]),
        );
        if (response.ok) return response.body;
        if (!validator.validate(SCHEMA_REFS.errorResponse, response.body).valid) {
            throw mismatch(`http_${response.status}`);
        }
        throw ContextServiceError.fromApiError((response.body as ErrorResponse).error);
    }

    function job(body: unknown, workspaceId: string): PdfJobStatus {
        const status = validator.parse<PdfJobStatus>(SCHEMA_REFS.pdfJobStatus, body);
        if (status.workspace_id !== workspaceId) throw mismatch("workspace_mismatch");
        return status;
    }

    return {
        async parse(workspaceId, pointer, idempotencyKey, signal) {
            const body = await call(
                "/internal/v1/pdf/parse",
                workspaceId,
                { pointer, idempotency_key: idempotencyKey },
                signal,
            );
            return job(body, workspaceId);
        },
        async status(workspaceId, jobId, signal) {
            return job(await call("/internal/v1/pdf/status", workspaceId, { job_id: jobId }, signal), workspaceId);
        },
        async readPages(workspaceId, request, signal) {
            const selector = {
                type: "pdf_page",
                start: request.startPage,
                ...(request.endPage === undefined ? {} : { end: request.endPage }),
            };
            const body = await call(
                "/internal/v1/source/read",
                workspaceId,
                {
                    pointer: request.pointer,
                    selector,
                    ...(request.maxBytes === undefined ? {} : { max_bytes: request.maxBytes }),
                    ...(request.maxTokens === undefined ? {} : { max_tokens: request.maxTokens }),
                    ...(request.cursor === undefined ? {} : { cursor: request.cursor }),
                },
                signal,
            );
            const result = validator.parse<PointerReadResult>(SCHEMA_REFS.pointerReadResult, body);
            const range = result.provenance.selection?.range;
            if (result.pointer !== request.pointer || (range !== undefined && range.type !== "pdf_page")) {
                throw mismatch("pointer_or_range_mismatch");
            }
            return result;
        },
        async search(workspaceId, request, signal) {
            const body = await call("/internal/v1/source/search", workspaceId, request, signal);
            const result = validator.parse<PointerSearchResult>(SCHEMA_REFS.pointerSearchResult, body);
            if (result.pointer !== request.pointer) throw mismatch("pointer_mismatch");
            return result;
        },
    };
}
