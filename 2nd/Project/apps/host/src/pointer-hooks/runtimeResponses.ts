/** Scope and response checks shared by the Runtime client and the streaming upload. */
import { SCHEMA_REFS, type ContractValidator, type PointerDescriptor } from "@securecode/contracts";
import type { RuntimeScope, StoredRuntimeOutput } from "../cline/adapter/ports.js";
import { ContextServiceError } from "../context-client/contextServiceError.js";

const SCOPE_SEGMENT = /^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}$/;

export function runtimePrefix(scope: RuntimeScope): string {
    if (!SCOPE_SEGMENT.test(scope.workspaceId) || !SCOPE_SEGMENT.test(scope.sessionId)) {
        throw new ContextServiceError("FORBIDDEN", "invalid runtime pointer scope", false);
    }
    return `securecode://runtime/${scope.workspaceId}/${scope.sessionId}/`;
}

export function invalidResponse(reason: string): ContextServiceError {
    return new ContextServiceError("SERVICE_UNAVAILABLE", "runtime store returned an invalid response", true, {
        reason,
    });
}

/** Validates a store/stream response: descriptor contract, scope prefix and byte count. */
export function storedFrom(
    body: unknown,
    scope: RuntimeScope,
    validator: ContractValidator,
    expectedBytes?: number,
): StoredRuntimeOutput {
    const record = body as { pointer_uri?: unknown; byte_size?: unknown; descriptor?: unknown };
    const descriptor = validator.parse<PointerDescriptor>(SCHEMA_REFS.pointerDescriptor, record.descriptor);
    const pointer = record.pointer_uri;
    if (typeof pointer !== "string" || pointer !== descriptor.pointer || !pointer.startsWith(runtimePrefix(scope))) {
        throw invalidResponse("scope_mismatch");
    }
    if (
        record.byte_size !== descriptor.byte_size ||
        (expectedBytes !== undefined && expectedBytes !== record.byte_size)
    ) {
        throw invalidResponse("byte_count_mismatch");
    }
    return { pointer, byteSize: descriptor.byte_size };
}
