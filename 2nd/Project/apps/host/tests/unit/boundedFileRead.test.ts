/** Byte caps, UTF-8 continuation and large-file regressions for the SDK read tool. */
import assert from "node:assert/strict";
import { closeSync, ftruncateSync, mkdtempSync, openSync, rmSync, writeFileSync, writeSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import { readBoundedUtf8 } from "../../src/cline/tools/boundedFileRead.js";

it("reads a small range from a sparse 1 GiB file without allocating the file", () => {
    const root = mkdtempSync(join(tmpdir(), "securecode-bounded-"));
    try {
        const path = join(root, "large.txt");
        const file = openSync(path, "w");
        try {
            ftruncateSync(file, 1024 ** 3);
            writeSync(file, Buffer.from("tail"), 0, 4, 1024 ** 3 - 4);
        } finally {
            closeSync(file);
        }
        assert.equal(readBoundedUtf8(path, 1024 ** 3 - 4, 4), "tail");
        assert.match(readBoundedUtf8(path, 0, 8), /offset_bytes=8/);
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});

it("keeps byte cursors at complete UTF-8 characters and rejects invalid ranges", () => {
    const root = mkdtempSync(join(tmpdir(), "securecode-utf8-"));
    try {
        const path = join(root, "text.txt");
        writeFileSync(path, "a한글z");
        assert.match(readBoundedUtf8(path, 0, 3), /^a\n.*offset_bytes=1/);
        assert.match(readBoundedUtf8(path, 1, 4), /^한\n.*offset_bytes=4/);
        assert.equal(readBoundedUtf8(path, 4, 4), "글z");
        assert.throws(() => readBoundedUtf8(path, 2, 4));
        assert.throws(() => readBoundedUtf8(path, 1, 1));
        assert.throws(() => readBoundedUtf8(path, 0, -1));
        assert.throws(() => readBoundedUtf8(root, 0, 8));
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});
