/** Reads a bounded UTF-8 byte range without loading the remainder of a file. */
import { closeSync, constants, fstatSync, openSync, readSync } from "node:fs";

export function readBoundedUtf8(path: string, offset: number, limit: number): string {
    if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 65536) {
        throw new Error("invalid file byte range");
    }
    const file = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    try {
        const before = fstatSync(file);
        if (!before.isFile()) throw new Error("only regular files can be read");
        // Four lookahead bytes let us recognize a UTF-8 sequence at the range boundary.
        const bytes = Buffer.alloc(limit + 4);
        const count = readSync(file, bytes, 0, bytes.length, offset);
        let end = Math.min(count, limit);
        while (end > 0 && end < count && ((bytes[end] ?? 0) & 0xc0) === 0x80) end -= 1;
        if (count > 0 && end === 0) throw new Error("max_bytes cannot fit the next UTF-8 character");
        const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes.subarray(0, end));
        const after = fstatSync(file);
        if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs) {
            throw new Error("file changed during read");
        }
        const next = offset + end;
        return (
            text +
            (next < before.size
                ? `\n[read_file: bytes ${offset}-${next} of ${before.size}; call again with offset_bytes=${next}]`
                : "")
        );
    } finally {
        closeSync(file);
    }
}
