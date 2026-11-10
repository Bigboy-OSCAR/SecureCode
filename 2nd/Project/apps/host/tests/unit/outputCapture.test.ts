/** 4.4 executor streaming: inline vs streamed capture, bounded host memory, capture cap, sink failure and abort. */
import assert from "node:assert/strict";
import { it } from "node:test";
import type { RuntimeUpload } from "../../src/cline/adapter/ports.js";
import { runCommand } from "../../src/cline/tools/commandRunner.js";
import { OutputCapture } from "../../src/cline/tools/outputCapture.js";

class RecordingUpload implements RuntimeUpload {
    readonly chunks: Buffer[] = [];
    aborted = false;
    failAfter = Infinity;

    async write(chunk: Uint8Array): Promise<void> {
        if (this.chunks.length >= this.failAfter) throw new Error("store went away");
        this.chunks.push(Buffer.from(chunk));
    }

    async finish() {
        const text = Buffer.concat(this.chunks).toString("utf8");
        return {
            pointer: "securecode://runtime/ws_12345678/ses_12345678/11111111-2222-4333-8444-555555555555?v=1",
            byteSize: Buffer.byteLength(text),
        };
    }

    abort(): void {
        this.aborted = true;
    }

    text(): string {
        return Buffer.concat(this.chunks).toString("utf8");
    }
}

function capture(upload: RecordingUpload, maxStoredBytes = 32 * 1024 * 1024): OutputCapture {
    return new OutputCapture({ thresholdBytes: 4096, maxStoredBytes, open: () => upload });
}

it("keeps small output inline and never opens an upload", async () => {
    const upload = new RecordingUpload();
    const sink = capture(upload);
    await sink.append("short output\n");
    assert.deepEqual(await sink.finish("[run_command: exit code 0]"), {
        kind: "inline",
        text: "short output\n\n[run_command: exit code 0]",
    });
    assert.equal(upload.chunks.length, 0);
});

it("streams large output with bounded host buffering and a clean UTF-8 preview", async () => {
    const upload = new RecordingUpload();
    const sink = capture(upload);
    const piece = "로그 줄 데이터 ".repeat(500);
    let peak = 0;
    for (let index = 0; index < 200; index += 1) {
        await sink.append(piece);
        peak = Math.max(peak, sink.bufferedBytes);
    }
    const result = await sink.finish("[run_command: exit code 0]");
    assert.equal(result.kind, "stored");
    assert.ok(peak < 4096 + Buffer.byteLength(piece), `peak buffered ${peak}`);
    assert.equal(upload.text(), `${piece.repeat(200)}\n[run_command: exit code 0]`);
    if (result.kind === "stored") {
        assert.ok(Buffer.byteLength(result.preview) <= 512 && !result.preview.includes("�"));
        assert.equal(result.truncated, false);
        assert.equal(result.producedBytes, Buffer.byteLength(piece) * 200);
    }
});

it("caps stored bytes, counts the rest and records the cut in the stored object", async () => {
    const upload = new RecordingUpload();
    const sink = capture(upload, 64 * 1024);
    for (let index = 0; index < 50; index += 1) await sink.append("x".repeat(4096));
    const result = await sink.finish("[run_command: exit code 0]");
    assert.ok(result.kind === "stored" && result.truncated && result.producedBytes === 50 * 4096);
    const stored = upload.text();
    assert.ok(Buffer.byteLength(stored) <= 64 * 1024);
    assert.match(
        stored,
        /output truncated before storage; kept 64512 of 204800 bytes\]\n\[run_command: exit code 0\]$/,
    );
});

it("streams a real command's output through backpressure and keeps arrival order", async () => {
    const received: string[] = [];
    const script = "for (let i = 0; i < 20000; i++) process.stdout.write('line-' + i + '\\n')";
    const result = await runCommand(`node -e "${script}"`, {
        cwd: process.cwd(),
        timeoutMs: 20000,
        onOutput: async (text) => {
            received.push(text);
            await new Promise((resolve) => setTimeout(resolve, 0));
        },
    });
    assert.equal(result.exitCode, 0);
    const lines = received.join("").trimEnd().split(/\r?\n/);
    assert.equal(lines.length, 20000);
    assert.equal(lines[19999], "line-19999");
    assert.ok(received.length > 1);
});

it("stops the command when the sink fails and when the run is aborted", async () => {
    const script = "setInterval(() => process.stdout.write('x'.repeat(65536)), 1)";
    await assert.rejects(
        runCommand(`node -e "${script}"`, {
            cwd: process.cwd(),
            timeoutMs: 20000,
            onOutput: () => Promise.reject(new Error("store went away")),
        }),
        /store went away/,
    );
    const controller = new AbortController();
    setTimeout(() => controller.abort(), 200);
    const aborted = await runCommand(`node -e "${script}"`, {
        cwd: process.cwd(),
        timeoutMs: 20000,
        signal: controller.signal,
        onOutput: async () => undefined,
    });
    assert.equal(aborted.aborted, true);
});
