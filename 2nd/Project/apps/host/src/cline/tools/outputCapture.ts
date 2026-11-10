/**
 * Project-owned capture of one command output. Small outputs stay inline. Once the output reaches
 * the pointer threshold, the buffered head and every later chunk stream into the Runtime store, so
 * host memory holds at most the head plus one chunk. Bytes beyond maxStoredBytes are counted but
 * dropped, and the stored object ends with a note saying how much was kept.
 */
import type { RuntimeUpload, StoredRuntimeOutput } from "../adapter/ports.js";

const TRAILER_RESERVE_BYTES = 1024;
const PREVIEW_BYTES = 512;

export interface CaptureOptions {
    thresholdBytes: number;
    maxStoredBytes: number;
    open(): RuntimeUpload;
}

export type CaptureResult =
    | { kind: "inline"; text: string }
    | {
          kind: "stored";
          stored: StoredRuntimeOutput;
          preview: string;
          producedBytes: number;
          truncated: boolean;
      };

function clipToBytes(text: string, maxBytes: number): Buffer {
    const bytes = Buffer.from(text, "utf8");
    if (bytes.length <= maxBytes) return bytes;
    let end = maxBytes;
    while (end > 0 && ((bytes[end] ?? 0) & 0xc0) === 0x80) end -= 1;
    return bytes.subarray(0, end);
}

/** Drops a trailing incomplete UTF-8 sequence (the preview is cut at a fixed byte count). */
function completeUtf8(bytes: Buffer): Buffer {
    let start = bytes.length - 1;
    while (start > 0 && ((bytes[start] ?? 0) & 0xc0) === 0x80) start -= 1;
    const lead = bytes[start] ?? 0;
    const width = lead >= 0xf0 ? 4 : lead >= 0xe0 ? 3 : lead >= 0xc0 ? 2 : 1;
    return start + width > bytes.length ? bytes.subarray(0, start) : bytes;
}

export class OutputCapture {
    private head = "";
    private headBytes = 0;
    private upload: RuntimeUpload | null = null;
    private produced = 0;
    private stored = 0;
    private truncated = false;
    private preview = Buffer.alloc(0);

    constructor(private readonly options: CaptureOptions) {
        if (options.maxStoredBytes <= options.thresholdBytes + TRAILER_RESERVE_BYTES) {
            throw new Error("capture limit must exceed the pointer threshold");
        }
    }

    /** Peak bytes held in host memory for this capture (head buffer); exposed for tests. */
    get bufferedBytes(): number {
        return this.headBytes;
    }

    async append(text: string): Promise<void> {
        const size = Buffer.byteLength(text, "utf8");
        this.produced += size;
        if (this.upload === null) {
            this.head += text;
            this.headBytes += size;
            if (this.headBytes < this.options.thresholdBytes) return;
            this.upload = this.options.open();
            const head = this.head;
            this.head = "";
            this.headBytes = 0;
            await this.write(head);
            return;
        }
        await this.write(text);
    }

    async finish(status: string): Promise<CaptureResult> {
        if (this.upload === null) {
            const text = `${this.head}\n${status}`;
            if (Buffer.byteLength(text, "utf8") < this.options.thresholdBytes) return { kind: "inline", text };
            this.upload = this.options.open();
            const head = this.head;
            this.head = "";
            this.headBytes = 0;
            await this.write(head);
        }
        const note = this.truncated
            ? `\n[securecode: output truncated before storage; kept ${this.stored} of ${this.produced} bytes]`
            : "";
        await this.upload.write(Buffer.from(`${note}\n${status}`, "utf8"));
        const stored = await this.upload.finish();
        return {
            kind: "stored",
            stored,
            preview: completeUtf8(this.preview).toString("utf8"),
            producedBytes: this.produced,
            truncated: this.truncated,
        };
    }

    abort(): void {
        this.upload?.abort();
    }

    private async write(text: string): Promise<void> {
        const room = this.options.maxStoredBytes - TRAILER_RESERVE_BYTES - this.stored;
        if (room <= 0) {
            this.truncated ||= text.length > 0;
            return;
        }
        const bytes = clipToBytes(text, room);
        this.truncated ||= bytes.length < Buffer.byteLength(text, "utf8");
        if (this.preview.length < PREVIEW_BYTES) {
            this.preview = Buffer.concat([this.preview, bytes.subarray(0, PREVIEW_BYTES - this.preview.length)]);
        }
        this.stored += bytes.length;
        if (bytes.length > 0 && this.upload) await this.upload.write(bytes);
    }
}
