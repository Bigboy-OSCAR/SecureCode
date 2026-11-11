/** Keeps native app state outside project folders and migrates the old local state once, without deleting it. */
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { currentInstance, devDataDir } from "../dev/state.js";

const STATE_ENTRIES = ["host", "cline", "derived", "runtime", "sources", "symbols", "workspaces.json"];
const STORAGE_PATHS = ["transcript_path", "hook_path", "messages_path"] as const;

/** Repoints SDK-owned storage paths without changing workspace paths or message contents. */
function rebaseSdkStorage(staged: string, source: string, destination: string): void {
    const oldPrefix = resolve(source) + "/";
    const rebase = (value: unknown): unknown =>
        typeof value === "string" && value.startsWith(oldPrefix)
            ? resolve(destination) + "/" + value.slice(oldPrefix.length)
            : value;
    const sessions = join(staged, "cline", "data", "sessions");
    if (existsSync(sessions)) {
        for (const file of readdirSync(sessions, { recursive: true, withFileTypes: true })) {
            if (!file.isFile() || !file.name.endsWith(".json") || file.name.endsWith(".messages.json")) continue;
            const path = join(file.parentPath, file.name);
            const record = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
            let changed = false;
            for (const key of STORAGE_PATHS) {
                const updated = rebase(record[key]);
                if (updated !== record[key]) {
                    record[key] = updated;
                    changed = true;
                }
            }
            if (changed) writeFileSync(path, JSON.stringify(record) + "\n", { mode: 0o600 });
        }
    }
    const path = join(staged, "cline", "data", "db", "sessions.db");
    if (!existsSync(path)) return;
    const database = new DatabaseSync(path);
    try {
        const columns = database
            .prepare("PRAGMA table_info(sessions)")
            .all()
            .map((column) => column.name);
        for (const column of STORAGE_PATHS.filter((name) => columns.includes(name))) {
            const update = database.prepare(`UPDATE sessions SET ${column} = ? WHERE session_id = ?`);
            for (const row of database.prepare(`SELECT session_id, ${column} FROM sessions`).all()) {
                const value = rebase(row[column]);
                if (value !== row[column] && typeof row.session_id === "string")
                    update.run(value as string, row.session_id);
            }
        }
    } finally {
        database.close();
    }
}

export function migrateDesktopData(source: string, destination: string): void {
    if (resolve(source) === resolve(destination) || existsSync(destination)) return;
    const previous = currentInstance(source);
    if (previous) {
        try {
            process.kill(previous.launcherPid, 0);
            throw new Error("이전 LocalDesk 실행을 종료한 뒤 앱을 다시 여세요.");
        } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
        }
    }
    mkdirSync(dirname(destination), { recursive: true, mode: 0o700 });
    const staged = `${destination}.migration-${randomUUID()}`;
    mkdirSync(staged, { mode: 0o700 });
    try {
        for (const entry of STATE_ENTRIES) {
            const from = join(source, entry);
            if (existsSync(from))
                cpSync(from, join(staged, entry), { recursive: true, errorOnExist: true, force: false });
        }
        rebaseSdkStorage(staged, source, destination);
        writeFileSync(
            join(staged, "migration.json"),
            JSON.stringify({ schema_version: "1", completed_at: new Date().toISOString() }) + "\n",
            { mode: 0o600 },
        );
        renameSync(staged, destination);
    } finally {
        rmSync(staged, { recursive: true, force: true });
    }
}

export function desktopDataDir(): string {
    const previous = devDataDir(); // Loads server/model settings from .env; its data directory remains CLI-only.
    const destination = resolve(
        process.env.LOCALDESK_DATA_DIR?.trim() || join(homedir(), "Library", "Application Support", "LocalDesk"),
    );
    migrateDesktopData(previous, destination);
    process.env.SECURECODE_DATA_DIR = destination;
    process.env.SECURECODE_CLINE_HOME = join(destination, "cline");
    return destination;
}
