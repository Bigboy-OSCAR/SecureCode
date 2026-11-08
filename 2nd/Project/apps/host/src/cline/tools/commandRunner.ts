/**
 * Runs one approved shell command in the workspace root with a timeout, an
 * output cap and the SDK's abort signal. Secrets and SDK paths are removed
 * from the child environment so commands cannot read them.
 */
import { spawn } from "node:child_process";

export interface CommandResult {
    exitCode: number | null;
    output: string;
    truncated: boolean;
    timedOut: boolean;
    aborted: boolean;
}

export interface CommandOptions {
    cwd: string;
    timeoutMs: number;
    maxOutputBytes: number;
    signal?: AbortSignal | undefined;
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
            stdio: ["ignore", "pipe", "pipe"],
        });
        const chunks: Buffer[] = [];
        let size = 0;
        let truncated = false;
        let timedOut = false;
        let aborted = false;
        const collect = (chunk: Buffer): void => {
            if (size >= options.maxOutputBytes) {
                truncated = true;
                return;
            }
            const room = options.maxOutputBytes - size;
            const kept = chunk.length > room ? chunk.subarray(0, room) : chunk;
            truncated ||= kept.length < chunk.length;
            chunks.push(kept);
            size += kept.length;
        };
        child.stdout.on("data", collect);
        child.stderr.on("data", collect);
        const stop = (): void => {
            child.kill("SIGTERM");
        };
        const timer = setTimeout(() => {
            timedOut = true;
            stop();
        }, options.timeoutMs);
        const onAbort = (): void => {
            aborted = true;
            stop();
        };
        options.signal?.addEventListener("abort", onAbort, { once: true });
        child.once("error", (error) => {
            clearTimeout(timer);
            options.signal?.removeEventListener("abort", onAbort);
            reject(error);
        });
        child.once("close", (exitCode) => {
            clearTimeout(timer);
            options.signal?.removeEventListener("abort", onAbort);
            const output = new TextDecoder("utf-8").decode(Buffer.concat(chunks));
            resolve({ exitCode, output, truncated, timedOut, aborted });
        });
    });
}
