/**
 * Public pointer routes (3.6): Source registration/refresh, pointer listing, bounded read/search and
 * deletion. The workspace (and, for Runtime Pointers, the session) comes from the pointer URI and must
 * exist in the host; the context-service re-checks scope, external-file grants and byte/token caps.
 */
import {
    SCHEMA_REFS,
    type PointerDeleteRequest,
    type PointerDeleteResult,
    type PointerListQuery,
    type PointerReadRequest,
    type PointerSearchRequest,
    type SourceMutationRequest,
} from "@securecode/contracts";
import { requestUrl, type RouteServices } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler, Router } from "../router.js";
import { validateBody, readContractBody } from "../shared/requestBody.js";
import { RouteFailure } from "../shared/routeFailure.js";

const SOURCE_URI = /^securecode:\/\/source\/(ws_[A-Za-z0-9-]{8,64})\//;
const RUNTIME_URI = /^securecode:\/\/runtime\/(ws_[A-Za-z0-9-]{8,64})\/(ses_[A-Za-z0-9-]{8,64})\//;

type Scope = { kind: "source"; workspaceId: string } | { kind: "runtime"; workspaceId: string; sessionId: string };

/** Scope of a pointer URI, checked against the host's workspaces and sessions. */
export function pointerScope(services: RouteServices, pointer: string): Scope {
    const source = SOURCE_URI.exec(pointer);
    if (source?.[1]) {
        services.workspaces.get(source[1]);
        return { kind: "source", workspaceId: source[1] };
    }
    const runtime = RUNTIME_URI.exec(pointer);
    if (runtime?.[1] && runtime[2]) {
        const session = services.sessions.get(runtime[2]);
        if (session.workspace_id !== runtime[1]) throw new RouteFailure("FORBIDDEN", "pointer is outside its session");
        return { kind: "runtime", workspaceId: runtime[1], sessionId: runtime[2] };
    }
    throw new RouteFailure("INVALID_POINTER", "pointer URI is not recognised");
}

/** The request body without schema_version (the host client adds it for the internal call). */
function withoutVersion<T extends { schema_version: string }>(body: T): Omit<T, "schema_version"> {
    const copy: Partial<T> = { ...body };
    delete copy.schema_version;
    return copy as Omit<T, "schema_version">;
}

function listQuery(url: URL): PointerListQuery {
    const query: Record<string, unknown> = {};
    for (const [key, value] of url.searchParams) query[key] = key === "limit" ? Number(value) : value;
    return query as unknown as PointerListQuery;
}

export function registerPointerRoutes(router: Router, services: RouteServices): void {
    const { contextClient: client, validator } = services;

    const mutate: RouteHandler = async ({ request, response, params }) => {
        const workspaceId = params.workspace_id ?? "";
        services.workspaces.get(workspaceId);
        const body = await readContractBody<SourceMutationRequest>(
            request,
            validator,
            SCHEMA_REFS.sourceMutationRequest,
        );
        await services.serviceWorkspaces.ensure(workspaceId);
        sendJson(response, 200, await client.sources.mutate(workspaceId, body));
    };

    const list: RouteHandler = async ({ request, response, params }) => {
        const workspaceId = params.workspace_id ?? "";
        services.workspaces.get(workspaceId);
        const query = validateBody<PointerListQuery>(
            validator,
            SCHEMA_REFS.pointerListQuery,
            listQuery(requestUrl(request.url)),
        );
        const page = {
            ...(query.limit ? { limit: query.limit } : {}),
            ...(query.cursor ? { cursor: query.cursor } : {}),
        };
        if (query.kind === "source") {
            await services.serviceWorkspaces.ensure(workspaceId);
            sendJson(response, 200, await client.sources.list(workspaceId, page));
            return;
        }
        const session = services.sessions.get(query.session_id);
        if (session.workspace_id !== workspaceId)
            throw new RouteFailure("FORBIDDEN", "session is outside this workspace");
        sendJson(response, 200, await client.runtime.list({ workspaceId, sessionId: query.session_id }, page));
    };

    const read: RouteHandler = async ({ request, response }) => {
        const body = await readContractBody<PointerReadRequest>(request, validator, SCHEMA_REFS.pointerReadRequest);
        const scope = pointerScope(services, body.pointer);
        const rest = withoutVersion(body);
        if (scope.kind === "source") {
            await services.serviceWorkspaces.ensure(scope.workspaceId);
            sendJson(response, 200, await client.sources.read(scope.workspaceId, rest));
            return;
        }
        const runtime = services.runtimePointers;
        if (!runtime) throw new RouteFailure("PROTECTION_UNAVAILABLE", "runtime store is not configured");
        sendJson(response, 200, await runtime.read(scope, rest, AbortSignal.timeout(15000)));
    };

    const search: RouteHandler = async ({ request, response }) => {
        const body = await readContractBody<PointerSearchRequest>(request, validator, SCHEMA_REFS.pointerSearchRequest);
        const scope = pointerScope(services, body.pointer);
        const rest = withoutVersion(body);
        if (scope.kind === "source") {
            await services.serviceWorkspaces.ensure(scope.workspaceId);
            sendJson(response, 200, await client.sources.search(scope.workspaceId, rest));
            return;
        }
        const runtime = services.runtimePointers;
        if (!runtime) throw new RouteFailure("PROTECTION_UNAVAILABLE", "runtime store is not configured");
        sendJson(response, 200, await runtime.search(scope, rest, AbortSignal.timeout(15000)));
    };

    const remove: RouteHandler = async ({ request, response }) => {
        const body = await readContractBody<PointerDeleteRequest>(request, validator, SCHEMA_REFS.pointerDeleteRequest);
        const scope = pointerScope(services, body.pointer);
        if (scope.workspaceId !== body.workspace_id)
            throw new RouteFailure("FORBIDDEN", "pointer is outside this workspace");
        if (scope.kind === "source") {
            await services.serviceWorkspaces.ensure(scope.workspaceId);
            sendJson(
                response,
                200,
                await client.sources.unregister(scope.workspaceId, body.pointer, body.idempotency_key),
            );
            return;
        }
        await client.runtime.remove(scope, body.pointer);
        const result: PointerDeleteResult = {
            schema_version: "1",
            effect: "runtime_deleted",
            kind: "runtime",
            pointer: body.pointer,
            workspace_id: scope.workspaceId,
            session_id: scope.sessionId,
        };
        sendJson(response, 200, result);
    };

    router.add("POST", "/api/v1/workspaces/:workspace_id/sources", mutate);
    router.add("GET", "/api/v1/workspaces/:workspace_id/pointers", list);
    router.add("POST", "/api/v1/pointers/read", read);
    router.add("POST", "/api/v1/pointers/search", search);
    router.add("DELETE", "/api/v1/pointers", remove);
}
