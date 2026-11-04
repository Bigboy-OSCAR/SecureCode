/**
 * Locates and loads the contract JSON Schema files. Shared by the runtime
 * validator, the type generator and the fixture tests so all three see the
 * same schema set.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

/** Contract areas in load order. pointers/ and context/ are owned by 4.2 and may still be empty. */
export const CONTRACT_AREAS = ["common", "api", "events", "symbols", "pointers", "context"] as const;

export interface SchemaFile {
    /** Path relative to the contracts root with forward slashes, e.g. "api/run.schema.json". */
    relativePath: string;
    schema: Record<string, unknown>;
}

export function resolveContractsRoot(): string {
    return join(dirname(fileURLToPath(import.meta.url)), "..");
}

function listJsonFiles(directory: string, suffix: string): string[] {
    let entries: string[];
    try {
        entries = readdirSync(directory, { recursive: true, encoding: "utf8" });
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") {
            return [];
        }
        throw error;
    }
    return entries.filter((entry) => entry.endsWith(suffix)).map((entry) => join(directory, entry));
}

export function toPosixRelative(root: string, filePath: string): string {
    return relative(root, filePath).split(sep).join("/");
}

export function loadSchemaFiles(contractsRoot: string = resolveContractsRoot()): SchemaFile[] {
    const files: SchemaFile[] = [];
    for (const area of CONTRACT_AREAS) {
        for (const filePath of listJsonFiles(join(contractsRoot, area), ".schema.json").sort()) {
            const schema = JSON.parse(readFileSync(filePath, "utf8")) as Record<string, unknown>;
            files.push({ relativePath: toPosixRelative(contractsRoot, filePath), schema });
        }
    }
    return files;
}

export function listFixtureFiles(contractsRoot: string = resolveContractsRoot()): string[] {
    return listJsonFiles(join(contractsRoot, "fixtures"), ".json").sort();
}
