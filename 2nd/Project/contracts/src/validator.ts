/**
 * Runtime validator for contract payloads. Consumers validate untrusted JSON
 * (HTTP bodies, context-service responses, fixtures) against the same schema
 * files the Python service tests use, instead of re-declaring shapes by hand.
 */
import Ajv, { type ErrorObject, type ValidateFunction } from "ajv";
import addFormats from "ajv-formats";
import { loadSchemaFiles, resolveContractsRoot } from "./schemaFiles.js";

/** Never fetched: schemas are registered under this base so relative $refs resolve offline. */
export const CONTRACT_BASE_URI = "https://contracts.securecode.invalid/";

export interface ContractValidationResult {
    valid: boolean;
    errors: string[];
}

export class ContractValidationError extends Error {
    readonly schemaRef: string;
    readonly errors: string[];

    constructor(schemaRef: string, errors: string[]) {
        super(`payload does not match ${schemaRef}: ${errors.slice(0, 3).join("; ")}`);
        this.name = "ContractValidationError";
        this.schemaRef = schemaRef;
        this.errors = errors;
    }
}

function formatErrors(errors: ErrorObject[] | null | undefined): string[] {
    return (errors ?? []).map((error) => `${error.instancePath || "/"} ${error.message ?? error.keyword}`);
}

export class ContractValidator {
    private readonly ajv: Ajv;
    private readonly compiled = new Map<string, ValidateFunction>();

    private constructor(ajv: Ajv) {
        this.ajv = ajv;
    }

    static load(contractsRoot: string = resolveContractsRoot()): ContractValidator {
        const ajv = new Ajv({ allErrors: true, strict: true, strictRequired: false, allowUnionTypes: true });
        addFormats(ajv);
        for (const file of loadSchemaFiles(contractsRoot)) {
            ajv.addSchema(file.schema, `${CONTRACT_BASE_URI}${file.relativePath}`);
        }
        return new ContractValidator(ajv);
    }

    /** schemaRef: "<area>/<file>.schema.json#/definitions/<Name>". */
    validate(schemaRef: string, data: unknown): ContractValidationResult {
        const validateFunction = this.getValidateFunction(schemaRef);
        const valid = validateFunction(data);
        return { valid, errors: valid ? [] : formatErrors(validateFunction.errors) };
    }

    /** Returns data typed as T when it matches; throws ContractValidationError otherwise. */
    parse<T>(schemaRef: string, data: unknown): T {
        const result = this.validate(schemaRef, data);
        if (!result.valid) {
            throw new ContractValidationError(schemaRef, result.errors);
        }
        return data as T;
    }

    private getValidateFunction(schemaRef: string): ValidateFunction {
        const cached = this.compiled.get(schemaRef);
        if (cached) {
            return cached;
        }
        const validateFunction = this.ajv.getSchema(`${CONTRACT_BASE_URI}${schemaRef}`);
        if (!validateFunction) {
            throw new Error(`unknown contract schema ref: ${schemaRef}`);
        }
        this.compiled.set(schemaRef, validateFunction);
        return validateFunction;
    }
}
