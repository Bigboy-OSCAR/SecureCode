import Ajv, { type ErrorObject } from "ajv";
import addFormats from "ajv-formats";
import { SCHEMA_REFS, type SchemaRefName } from "../../../../../contracts/src/schemaRefs.js";
import approvalSchema from "../../../../../contracts/api/approval.schema.json";
import runSchema from "../../../../../contracts/api/run.schema.json";
import sessionSchema from "../../../../../contracts/api/session.schema.json";
import systemSchema from "../../../../../contracts/api/system.schema.json";
import workspaceSchema from "../../../../../contracts/api/workspace.schema.json";
import apiErrorSchema from "../../../../../contracts/common/api-error.schema.json";
import paginationSchema from "../../../../../contracts/common/pagination.schema.json";
import primitivesSchema from "../../../../../contracts/common/primitives.schema.json";
import tokenCountSchema from "../../../../../contracts/common/token-count.schema.json";
import eventSchema from "../../../../../contracts/events/app-event.schema.json";
import contextSchema from "../../../../../contracts/context/context.schema.json";
import pdfJobSchema from "../../../../../contracts/pointers/pdf-job.schema.json";
import pointerSchema from "../../../../../contracts/pointers/pointer.schema.json";
import pointerLifecycleSchema from "../../../../../contracts/pointers/lifecycle.schema.json";
import pointerReadSchema from "../../../../../contracts/pointers/read.schema.json";
import pointerSearchSchema from "../../../../../contracts/pointers/search.schema.json";
import symbolSchema from "../../../../../contracts/symbols/symbol.schema.json";

const contractBaseUri = "https://contracts.securecode.invalid/";
const schemas = [
    ["api/approval.schema.json", approvalSchema],
    ["api/run.schema.json", runSchema],
    ["api/session.schema.json", sessionSchema],
    ["api/system.schema.json", systemSchema],
    ["api/workspace.schema.json", workspaceSchema],
    ["common/api-error.schema.json", apiErrorSchema],
    ["common/pagination.schema.json", paginationSchema],
    ["common/primitives.schema.json", primitivesSchema],
    ["common/token-count.schema.json", tokenCountSchema],
    ["context/context.schema.json", contextSchema],
    ["events/app-event.schema.json", eventSchema],
    ["pointers/lifecycle.schema.json", pointerLifecycleSchema],
    ["pointers/pdf-job.schema.json", pdfJobSchema],
    ["pointers/pointer.schema.json", pointerSchema],
    ["pointers/read.schema.json", pointerReadSchema],
    ["pointers/search.schema.json", pointerSearchSchema],
    ["symbols/symbol.schema.json", symbolSchema],
] as const;

const validator = createValidator();

export class InvalidApiPayloadError extends Error {
    constructor(schemaRef: string, errors: string[]) {
        super(`Host response does not match ${schemaRef}: ${errors.slice(0, 3).join("; ")}`);
        this.name = "InvalidApiPayloadError";
    }
}

export function parseApiPayload<T>(schemaRef: SchemaRefName, payload: unknown): T {
    const validate = validator.getSchema(`${contractBaseUri}${SCHEMA_REFS[schemaRef]}`);
    if (!validate) {
        throw new Error(`Unknown contract schema reference: ${schemaRef}`);
    }
    if (!validate(payload)) {
        const messages = (validate.errors ?? []).map(formatValidationError);
        throw new InvalidApiPayloadError(schemaRef, messages);
    }
    return payload as T;
}

export function serializeApiRequest(schemaRef: SchemaRefName, payload: unknown): unknown {
    const wirePayload = mapKeysToSnakeCase(payload);
    parseApiPayload(schemaRef, wirePayload);
    return wirePayload;
}

function mapKeysToSnakeCase(value: unknown): unknown {
    if (Array.isArray(value)) {
        return value.map(mapKeysToSnakeCase);
    }
    if (value === null || typeof value !== "object") {
        return value;
    }
    return Object.fromEntries(
        Object.entries(value).map(([key, nestedValue]) => [
            key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
            mapKeysToSnakeCase(nestedValue),
        ]),
    );
}

function createValidator(): Ajv {
    const ajv = new Ajv({ allErrors: true, strict: true, strictRequired: false, allowUnionTypes: true });
    addFormats(ajv);
    ajv.addKeyword({
        keyword: "maxUtf8Bytes",
        type: "string",
        schemaType: "number",
        metaSchema: { type: "integer", minimum: 0 },
        validate: (limit: number, value: string) =>
            value.isWellFormed() && new TextEncoder().encode(value).length <= limit,
    });
    for (const [path, schema] of schemas) {
        ajv.addSchema(schema, `${contractBaseUri}${path}`);
    }
    return ajv;
}

function formatValidationError(error: ErrorObject): string {
    return `${error.instancePath || "/"} ${error.message ?? error.keyword}`;
}
