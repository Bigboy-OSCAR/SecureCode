/** Public entry of @securecode/contracts: generated types, schema refs, validator and error table. */
export type * from "../generated/ts/contracts.js";
export { loadErrorCodeTable, type ErrorCodeRule, type ErrorCodeTable } from "./errorCodes.js";
export { SCHEMA_REFS, type SchemaRefName } from "./schemaRefs.js";
export { listFixtureFiles, loadSchemaFiles, resolveContractsRoot, type SchemaFile } from "./schemaFiles.js";
export {
    CONTRACT_BASE_URI,
    ContractValidationError,
    ContractValidator,
    type ContractValidationResult,
} from "./validator.js";

export type { LocalModel, ModelListResponse } from "./localModels.js";
export { parseModelListResponse } from "./localModels.js";
