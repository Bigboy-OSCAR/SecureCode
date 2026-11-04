/** Loads the TypeScript/Python shared vectors under the work root tests/fixtures. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

export const WORK_ROOT = join(fileURLToPath(import.meta.url), "..", "..", "..", "..", "..");

export function loadSharedVectors<T>(fileName: string): T {
    return JSON.parse(readFileSync(join(WORK_ROOT, "tests", "fixtures", fileName), "utf8")) as T;
}
