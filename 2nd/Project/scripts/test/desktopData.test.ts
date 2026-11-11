/** Migration copies only app state, keeps originals, excludes model weights and never overwrites a destination. */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import { DatabaseSync } from "node:sqlite";
import { migrateDesktopData } from "../desktop/dataDirectory.js";

it("moves the app data location by preserving state in a one-time copy and leaving original projects/models alone", () => {
    const root = mkdtempSync(join(tmpdir(), "localdesk-migrate-"));
    const source = join(root, "old");
    const target = join(root, "Application Support", "LocalDesk");
    for (const entry of ["host", "cline", "runtime", "models", "acceptance", "run"]) {
        mkdirSync(join(source, entry), { recursive: true });
        writeFileSync(join(source, entry, "sample"), entry);
    }
    const sessionDirectory = join("cline", "data", "sessions", "session");
    const metadataPath = join(sessionDirectory, "session.json");
    const messagesPath = join(sessionDirectory, "session.messages.json");
    mkdirSync(join(source, sessionDirectory), { recursive: true });
    const original = { messages_path: join(source, messagesPath), cwd: source, prompt: source };
    writeFileSync(join(source, metadataPath), JSON.stringify(original));
    writeFileSync(join(source, messagesPath), JSON.stringify({ messages: [{ content: source }] }));
    const databasePath = join("cline", "data", "db", "sessions.db");
    mkdirSync(join(source, "cline", "data", "db"), { recursive: true });
    const database = new DatabaseSync(join(source, databasePath));
    database.exec(
        "CREATE TABLE sessions (session_id TEXT, messages_path TEXT, transcript_path TEXT, hook_path TEXT, cwd TEXT)",
    );
    database
        .prepare("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)")
        .run("session", original.messages_path, join(source, "transcript"), "/external/hook", source);
    database.close();
    try {
        migrateDesktopData(source, target);
        assert.equal(readFileSync(join(target, "host", "sample"), "utf8"), "host");
        assert.equal(readFileSync(join(target, "runtime", "sample"), "utf8"), "runtime");
        for (const entry of ["models", "acceptance", "run"]) assert.equal(existsSync(join(target, entry)), false);
        assert.equal(readFileSync(join(source, "models", "sample"), "utf8"), "models");
        assert.deepEqual(JSON.parse(readFileSync(join(target, metadataPath), "utf8")), {
            ...original,
            messages_path: join(target, messagesPath),
        });
        assert.deepEqual(JSON.parse(readFileSync(join(source, metadataPath), "utf8")), original);
        assert.equal(
            readFileSync(join(target, messagesPath), "utf8"),
            readFileSync(join(source, messagesPath), "utf8"),
        );
        const migrated = new DatabaseSync(join(target, databasePath));
        assert.deepEqual(
            { ...migrated.prepare("SELECT * FROM sessions").get() },
            {
                session_id: "session",
                messages_path: join(target, messagesPath),
                transcript_path: join(target, "transcript"),
                hook_path: "/external/hook",
                cwd: source,
            },
        );
        migrated.close();
        writeFileSync(join(target, "host", "sample"), "new state");
        migrateDesktopData(source, target);
        assert.equal(readFileSync(join(target, "host", "sample"), "utf8"), "new state");
        assert.equal(readFileSync(join(source, "host", "sample"), "utf8"), "host");
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});
