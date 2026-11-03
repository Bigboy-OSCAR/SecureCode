/**
 * PROBE FIXTURE ONLY — NOT the Runtime Store.
 * An in-memory map used to prove the afterTool replacement path in task 3.1.
 * It has no persistence, TTL, session isolation, or size quota. The real
 * Runtime Pointer store is owned by task 4.3 (SQLite metadata + blob files).
 */
import { randomUUID } from "node:crypto";

export interface PointerDescriptorFixture {
    pointer: string;
    kind: "runtime";
    byte_size: number;
    preview: string;
    fixture_only: true;
}

export type PointerFailureMode = "none" | "throw" | "hang";

export class MemoryPointerFixture {
    readonly storedContents = new Map<string, string>();
    failureMode: PointerFailureMode = "none";

    async put(content: string, workspaceId: string, sessionId: string): Promise<PointerDescriptorFixture> {
        if (this.failureMode === "throw") {
            throw new Error("pointer fixture: injected storage failure");
        }
        if (this.failureMode === "hang") {
            await new Promise<never>(() => undefined);
        }

        const pointer = `securecode://runtime/${workspaceId}/${sessionId}/${randomUUID()}?v=1`;
        this.storedContents.set(pointer, content);
        return {
            pointer,
            kind: "runtime",
            byte_size: Buffer.byteLength(content, "utf8"),
            // The probe withholds previews so the sentinel cannot leak through them.
            preview: "[preview withheld by probe]",
            fixture_only: true,
        };
    }
}
