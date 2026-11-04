/**
 * Typed access to contracts/common/error-codes.json (HTTP status and default
 * retryability per ErrorCode). Python reads the same JSON file.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ErrorCode } from "../generated/ts/contracts.js";
import { resolveContractsRoot } from "./schemaFiles.js";

export interface ErrorCodeRule {
    http_status: number;
    retryable: boolean;
    owner_task: string;
    status: "final" | "draft";
    transport: "error_response" | "success_body";
}

export type ErrorCodeTable = Record<ErrorCode, ErrorCodeRule>;

export function loadErrorCodeTable(contractsRoot: string = resolveContractsRoot()): ErrorCodeTable {
    const raw = JSON.parse(readFileSync(join(contractsRoot, "common", "error-codes.json"), "utf8")) as {
        codes: ErrorCodeTable;
    };
    return raw.codes;
}
