/**
 * Minimal line logger. Every line goes through the Redactor, debug level
 * included, and is written to stderr so stdout stays free for launcher output.
 */
import type { LogLevel } from "../config/hostConfig.js";
import type { Redactor } from "./redaction.js";

const LEVEL_ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

export interface Logger {
    debug(message: string): void;
    info(message: string): void;
    warn(message: string): void;
    error(message: string): void;
}

export type LineWriter = (line: string) => void;

const writeToStderr: LineWriter = (line) => {
    process.stderr.write(line);
};

export function createLogger(level: LogLevel, redactor: Redactor, write: LineWriter = writeToStderr): Logger {
    const emit = (lineLevel: LogLevel, message: string): void => {
        if (LEVEL_ORDER[lineLevel] < LEVEL_ORDER[level]) {
            return;
        }
        write(`${new Date().toISOString()} ${lineLevel.toUpperCase()} host ${redactor.redact(message)}\n`);
    };
    return {
        debug: (message) => emit("debug", message),
        info: (message) => emit("info", message),
        warn: (message) => emit("warn", message),
        error: (message) => emit("error", message),
    };
}
