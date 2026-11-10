/**
 * Runs one approved shell command in the workspace root with a timeout and the SDK's abort signal.
 * Output is decoded per stream and handed to onOutput as it arrives; the child's pipes are paused
 * until onOutput settles, so a slow sink applies backpressure instead of buffering the whole output.
 * Secrets and SDK paths are removed from the child environment.
 */
import { spawn, type ChildProcess } from "node:child_process";
import type { Readable } from "node:stream";

export interface CommandResult {
    exitCode: number | null;
    timedOut: boolean;
    aborted: boolean;
}

export interface CommandOptions {
    cwd: string;
    timeoutMs: number;
    signal?: AbortSignal | undefined;
    /** Receives decoded output in arrival order; a rejection stops the command. */
    onOutput: (text: string) => Promise<void>;
}

const SECRET_ENV = /^(ANTHROPIC_API_KEY|SECURECODE_INTERNAL_TOKEN|SECURECODE_BOOTSTRAP_CODE|CLINE_.*)$/;

export function commandEnvironment(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
    const clean: NodeJS.ProcessEnv = {};
    for (const [name, value] of Object.entries(env)) {
        if (!SECRET_ENV.test(name)) clean[name] = value;
    }
    clean.GIT_TERMINAL_PROMPT = "0";
    return clean;
}

/**
 * Ends the command and everything it started. With shell: true the direct child is only the shell,
 * so killing it alone would leave the real process holding the pipes open.
 */
function killTree(child: ChildProcess): void {
    if (child.pid === undefined || child.exitCode !== null || child.signalCode !== null) return;
    if (process.platform === "win32") {
        spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" }).once(
            "error",
            () => child.kill(),
        );
        return;
    }
    try {
        process.kill(-child.pid, "SIGKILL");
    } catch {
        child.kill("SIGKILL");
    }
}

export function runCommand(command: string, options: CommandOptions): Promise<CommandResult> {
    return new Promise((resolve, reject) => {
        if (options.signal?.aborted) {
            reject(new Error("command aborted before start"));
            return;
        }
        const child = spawn(command, {
            cwd: options.cwd,
            shell: true,
            env: commandEnvironment(),
            windowsHide: true,
            // POSIX: own process group so killTree can end grandchildren too.
            detached: process.platform !== "win32",
            stdio: ["ignore", "pipe", "pipe"],
        });
        const streams: Readable[] = [child.stdout, child.stderr];
        let chain = Promise.resolve();
        let sinkError: unknown = null;
        let pending = 0;
        let timedOut = false;
        let aborted = false;
        const stop = (): void => killTree(child);
        const deliver = (text: string): void => {
            if (text === "" || sinkError !== null) return;
            pending += 1;
            for (const stream of streams) stream.pause();
            chain = chain
                .then(() => options.onOutput(text))
                .catch((error: unknown) => {
                    sinkError ??= error;
                    stop();
                })
                .finally(() => {
                    pending -= 1;
                    // After a sink failure keep draining (and dropping) so the child cannot block on a full pipe.
                    if (pending === 0 || sinkError !== null) for (const stream of streams) stream.resume();
                });
        };
        const decoders = streams.map((stream) => {
            const decoder = new TextDecoder("utf-8");
            stream.on("data", (chunk: Buffer) => deliver(decoder.decode(chunk, { stream: true })));
            return decoder;
        });
        const timer = setTimeout(() => {
            timedOut = true;
            stop();
        }, options.timeoutMs);
        const onAbort = (): void => {
            aborted = true;
            stop();
        };
        options.signal?.addEventListener("abort", onAbort, { once: true });
        const cleanup = (): void => {
            clearTimeout(timer);
            options.signal?.removeEventListener("abort", onAbort);
        };
        child.once("error", (error) => {
            cleanup();
            reject(error);
        });
        child.once("close", (exitCode) => {
            cleanup();
            for (const decoder of decoders) deliver(decoder.decode());
            void chain.then(() => {
                if (sinkError !== null)
                    reject(sinkError instanceof Error ? sinkError : new Error("output sink failed"));
                else resolve({ exitCode, timedOut, aborted });
            });
        });
    });
}
