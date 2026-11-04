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
} as const;

export type SchemaRefName = keyof typeof SCHEMA_REFS;
