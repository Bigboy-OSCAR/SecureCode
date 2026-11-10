/** One launched server process: output forwarding, exit tracking and an idempotent graceful stop. */
import { spawn, type ChildProcess } from "node:child_process";

export type OutputSink = (source: string, chunk: string) => void;

export interface LaunchedChild {
    child: ChildProcess;
    /** SIGTERM, then SIGKILL after 5 s; resolves once the process has closed. */
    stop: () => Promise<void>;
    exited: () => boolean;
}

export function launch(
    name: string,
    executable: string,
    args: string[],
    cwd: string,
    env: NodeJS.ProcessEnv,
    output: OutputSink | undefined,
): LaunchedChild {
    const child = spawn(executable, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    for (const stream of [child.stdout, child.stderr]) {
        stream.setEncoding("utf8");
        stream.on("data", (chunk: string) => output?.(name, chunk));
    }
    let ended = false;
    const closed = new Promise<void>((done) => {
        child.once("error", () => {
            ended = true;
            done();
        });
        child.once("close", () => {
            ended = true;
            done();
        });
    });
    let stopping: Promise<void> | undefined;
    function stop(): Promise<void> {
        stopping ??= (async () => {
            if (!ended && child.exitCode === null && child.signalCode === null) {
                child.kill("SIGTERM");
                const force = setTimeout(() => child.kill("SIGKILL"), 5000);
                try {
                    await closed;
                } finally {
                    clearTimeout(force);
                }
            } else await closed;
        })();
        return stopping;
    }
    return { child, stop, exited: () => ended || child.exitCode !== null || child.signalCode !== null };
}
