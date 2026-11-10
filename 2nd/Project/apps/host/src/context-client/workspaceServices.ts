/**
 * Host clients for the 3.6 service capabilities: workspace root registration, R0 index/search/bundle,
 * Source register/list/read/search/unregister and Runtime pointer list/delete. Every success body is
 * validated against its contract; scope (workspace, session) always comes from the host, never from
 * the browser body alone.
 */
import {
    SCHEMA_REFS,
    type IndexStatusResponse,
    type PointerDeleteResult,
    type PointerListResult,
    type PointerReadRequest,
    type PointerReadResult,
    type PointerSearchRequest,
    type PointerSearchResult,
    type SourceMutationRequest,
    type SourceMutationResult,
    type SymbolBundle,
    type SymbolBundleRequest,
    type SymbolSearchRequest,
    type SymbolSearchResponse,
} from "@securecode/contracts";
import { callService, parseAs, type ServiceCallOptions } from "./serviceCall.js";

type Body<T> = Omit<T, "schema_version">;

export interface WorkspaceService {
    register(workspaceId: string, rootPath: string, signal?: AbortSignal): Promise<void>;
    startIndex(workspaceId: string, signal?: AbortSignal): Promise<IndexStatusResponse>;
    indexStatus(workspaceId: string, signal?: AbortSignal): Promise<IndexStatusResponse>;
}

export interface SymbolService {
    search(request: SymbolSearchRequest, signal?: AbortSignal): Promise<SymbolSearchResponse>;
    readBundle(request: SymbolBundleRequest, signal?: AbortSignal): Promise<SymbolBundle>;
}

export interface SourceService {
    mutate(workspaceId: string, request: SourceMutationRequest, signal?: AbortSignal): Promise<SourceMutationResult>;
    list(
        workspaceId: string,
        page: { limit?: number; cursor?: string },
        signal?: AbortSignal,
    ): Promise<PointerListResult>;
    unregister(
        workspaceId: string,
        pointer: string,
        idempotencyKey: string,
        signal?: AbortSignal,
    ): Promise<PointerDeleteResult>;
    read(workspaceId: string, request: Body<PointerReadRequest>, signal?: AbortSignal): Promise<PointerReadResult>;
    search(
        workspaceId: string,
        request: Body<PointerSearchRequest>,
        signal?: AbortSignal,
    ): Promise<PointerSearchResult>;
}

export interface RuntimeAdminService {
    list(
        scope: { workspaceId: string; sessionId: string },
        page: { limit?: number; cursor?: string },
        signal?: AbortSignal,
    ): Promise<PointerListResult>;
    remove(scope: { workspaceId: string; sessionId: string }, pointer: string, signal?: AbortSignal): Promise<void>;
}

export function createWorkspaceService(options: ServiceCallOptions): WorkspaceService {
    const status = (body: unknown) => parseAs<IndexStatusResponse>(options, SCHEMA_REFS.indexStatusResponse, body);
    return {
        async register(workspaceId, rootPath, signal) {
            await callService(
                options,
                "/internal/v1/workspaces/register",
                { schema_version: "1", workspace_id: workspaceId, root_path: rootPath },
                signal,
            );
        },
        async startIndex(workspaceId, signal) {
            const body = { schema_version: "1", workspace_id: workspaceId };
            return status(await callService(options, "/internal/v1/symbols/index", body, signal));
        },
        async indexStatus(workspaceId, signal) {
            const body = { schema_version: "1", workspace_id: workspaceId };
            return status(await callService(options, "/internal/v1/symbols/index/status", body, signal));
        },
    };
}

export function createSymbolService(options: ServiceCallOptions): SymbolService {
    return {
        async search(request, signal) {
            const body = await callService(options, "/internal/v1/symbols/search", request, signal);
            return parseAs<SymbolSearchResponse>(options, SCHEMA_REFS.symbolSearchResponse, body);
        },
        async readBundle(request, signal) {
            const body = await callService(options, "/internal/v1/symbols/bundle", request, signal);
            return parseAs<SymbolBundle>(options, SCHEMA_REFS.symbolBundle, body);
        },
    };
}

export function createSourceService(options: ServiceCallOptions): SourceService {
    const scoped = (workspaceId: string, request: object) => ({
        schema_version: "1",
        workspace_id: workspaceId,
        ...request,
    });
    return {
        async mutate(workspaceId, request, signal) {
            const path = request.operation === "register" ? "register" : "refresh";
            const body = await callService(
                options,
                `/internal/v1/source/${path}`,
                scoped(workspaceId, request),
                signal,
            );
            return parseAs<SourceMutationResult>(options, SCHEMA_REFS.sourceMutationResult, body);
        },
        async list(workspaceId, page, signal) {
            // The internal list body is the PointerListQuery fields plus workspace (no schema_version).
            const request = { workspace_id: workspaceId, ...page };
            const body = await callService(options, "/internal/v1/source/list", request, signal);
            return parseAs<PointerListResult>(options, SCHEMA_REFS.pointerListResult, body);
        },
        async unregister(workspaceId, pointer, idempotencyKey, signal) {
            const request = { kind: "source", pointer, idempotency_key: idempotencyKey };
            const body = await callService(
                options,
                "/internal/v1/source/unregister",
                scoped(workspaceId, request),
                signal,
            );
            return parseAs<PointerDeleteResult>(options, SCHEMA_REFS.pointerDeleteResult, body);
        },
        async read(workspaceId, request, signal) {
            const body = await callService(options, "/internal/v1/source/read", scoped(workspaceId, request), signal);
            return parseAs<PointerReadResult>(options, SCHEMA_REFS.pointerReadResult, body);
        },
        async search(workspaceId, request, signal) {
            const body = await callService(options, "/internal/v1/source/search", scoped(workspaceId, request), signal);
            return parseAs<PointerSearchResult>(options, SCHEMA_REFS.pointerSearchResult, body);
        },
    };
}

export function createRuntimeAdminService(options: ServiceCallOptions): RuntimeAdminService {
    return {
        async list(scope, page, signal) {
            const request = {
                schema_version: "1",
                workspace_id: scope.workspaceId,
                session_id: scope.sessionId,
                ...page,
            };
            const body = await callService(options, "/internal/v1/runtime/list", request, signal);
            return parseAs<PointerListResult>(options, SCHEMA_REFS.pointerListResult, body);
        },
        async remove(scope, pointer, signal) {
            const request = { workspace_id: scope.workspaceId, session_id: scope.sessionId, pointer };
            await callService(options, "/internal/v1/runtime/pointers/delete", request, signal);
        },
    };
}
