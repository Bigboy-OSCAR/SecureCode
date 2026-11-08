/**
 * One JSON document per record under a host data directory. Writes go to a
 * temporary file that is renamed over the target, so a crash never leaves a
 * half-written record; unreadable files are skipped on load instead of failing startup.
 */
import { mkdirSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomBytes } from "node:crypto";

const RECORD_ID = /^[A-Za-z0-9_-]{1,96}$/;

export class JsonFileStore<T> {
    private readonly directory: string;

    constructor(directory: string) {
        this.directory = directory;
        mkdirSync(directory, { recursive: true, mode: 0o700 });
    }

    write(id: string, value: T): void {
        const target = this.pathFor(id);
        const temporary = `${target}.${randomBytes(6).toString("hex")}.tmp`;
        writeFileSync(temporary, JSON.stringify(value), { encoding: "utf8", mode: 0o600 });
        try {
            renameSync(temporary, target);
        } catch (error) {
            rmSync(temporary, { force: true });
            throw error;
        }
    }

    remove(id: string): void {
        rmSync(this.pathFor(id), { force: true });
    }

    loadAll(): T[] {
        const records: T[] = [];
        for (const name of readdirSync(this.directory)) {
            if (name.endsWith(".tmp")) {
                rmSync(join(this.directory, name), { force: true });
                continue;
            }
            if (!name.endsWith(".json")) continue;
            try {
                records.push(JSON.parse(readFileSync(join(this.directory, name), "utf8")) as T);
            } catch {
                // A corrupt record is ignored; the remaining state still loads.
            }
        }
        return records;
    }

    private pathFor(id: string): string {
        if (!RECORD_ID.test(id)) throw new Error("invalid record id");
        return join(this.directory, `${id}.json`);
    }
}
