/**
 * Named schema refs for the payloads the host validates at its boundaries.
 * Keep these in sync with the schema files; tests check every ref resolves.
 */
export const SCHEMA_REFS = {
    errorResponse: "common/api-error.schema.json#/definitions/ErrorResponse",
    tokenCountRequest: "common/token-count.schema.json#/definitions/TokenCountRequest",
    tokenCountResult: "common/token-count.schema.json#/definitions/TokenCountResult",
    healthResponse: "api/system.schema.json#/definitions/HealthResponse",
    serviceHealthResponse: "api/system.schema.json#/definitions/ServiceHealthResponse",
    settingsResponse: "api/system.schema.json#/definitions/SettingsResponse",
    runSnapshot: "api/run.schema.json#/definitions/RunSnapshot",
    appEvent: "events/app-event.schema.json#/definitions/AppEvent",
    symbolSearchRequest: "symbols/symbol.schema.json#/definitions/SymbolSearchRequest",
    symbolSearchResponse: "symbols/symbol.schema.json#/definitions/SymbolSearchResponse",
    symbolBundleRequest: "symbols/symbol.schema.json#/definitions/SymbolBundleRequest",
    symbolBundle: "symbols/symbol.schema.json#/definitions/SymbolBundle",
    pointerDescriptor: "pointers/pointer.schema.json#/definitions/PointerDescriptor",
    sourceRegistration: "pointers/pointer.schema.json#/definitions/SourceRegistration",
    runtimePutRequest: "pointers/pointer.schema.json#/definitions/RuntimePutRequest",
    pointerReadRequest: "pointers/read.schema.json#/definitions/PointerReadRequest",
    pointerReadResult: "pointers/read.schema.json#/definitions/PointerReadResult",
    pointerSearchRequest: "pointers/search.schema.json#/definitions/PointerSearchRequest",
    pointerSearchResult: "pointers/search.schema.json#/definitions/PointerSearchResult",
} as const;

export type SchemaRefName = keyof typeof SCHEMA_REFS;
