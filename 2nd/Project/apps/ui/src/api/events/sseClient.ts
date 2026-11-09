import type { AppEvent, RunId, Sequence } from "@securecode/contracts";
import { ApiClientError } from "../apiErrors.js";
import { InvalidApiPayloadError, parseApiPayload } from "../mappers/contractMapper.js";
import type { ApiFetch } from "../httpClient.js";

interface SseMessage {
    id: string | null;
    event: string | null;
    data: string[];
}

export class SseClient {
    constructor(
        private readonly baseUrl = "/api/v1",
        private readonly fetcher: ApiFetch = fetch,
        private readonly retryLimit = 6,
        private readonly idleTimeoutMs = 45000,
    ) {}

    subscribe(
        runId: RunId,
        afterSequence: Sequence,
        onEvent: (event: AppEvent) => void,
        onDisconnect: (error?: ApiClientError) => void,
        onReconnect?: () => void,
    ): () => void {
        const abortController = new AbortController();
        void this.consume(runId, afterSequence, abortController.signal, onEvent, onDisconnect, onReconnect);
        return () => abortController.abort();
    }

    private async consume(
        runId: RunId,
        afterSequence: Sequence,
        signal: AbortSignal,
        onEvent: (event: AppEvent) => void,
        onDisconnect: (error?: ApiClientError) => void,
        onReconnect?: () => void,
    ): Promise<void> {
        let lastSequence = afterSequence;
        let retryCount = 0;
        let disconnected = false;
        const path = `runs/${encodeURIComponent(runId)}/events`;

        while (!signal.aborted) {
            try {
                const response = await this.fetcher(`${this.baseUrl.replace(/\/$/, "")}/${path}`, {
                    method: "GET",
                    credentials: "same-origin",
                    headers: {
                        accept: "text/event-stream",
                        "last-event-id": String(lastSequence),
                    },
                    signal,
                });
                if (!response.ok) {
                    throw toStatusError(response.status);
                }
                if (!response.headers.get("content-type")?.toLowerCase().startsWith("text/event-stream")) {
                    throw new ApiClientError(
                        "contract",
                        "호스트가 유효한 이벤트 스트림을 반환하지 않았습니다.",
                        response.status,
                    );
                }
                if (!response.body) {
                    throw new ApiClientError("contract", "호스트 이벤트 스트림이 비어 있습니다.", response.status);
                }
                if (disconnected) {
                    disconnected = false;
                    onReconnect?.();
                }
                const terminal = await readEvents(
                    response.body,
                    runId,
                    this.idleTimeoutMs,
                    (event, id) => {
                        if (id !== null) {
                            lastSequence = Number(id);
                        }
                        onEvent(event);
                    },
                    signal,
                );
                if (terminal || signal.aborted) {
                    return;
                }
                throw new ApiClientError("network", "이벤트 스트림 연결이 종료되었습니다.");
            } catch (error) {
                if (signal.aborted) {
                    return;
                }
                const clientError = normalizeStreamError(error);
                if (!disconnected) {
                    disconnected = true;
                    onDisconnect(clientError);
                }
                if (!isRetryable(clientError) || retryCount >= this.retryLimit) {
                    return;
                }
                retryCount += 1;
                await delay(Math.min(250 * 2 ** (retryCount - 1), 4000), signal);
            }
        }
    }
}

async function readEvents(
    body: ReadableStream<Uint8Array>,
    expectedRunId: RunId,
    idleTimeoutMs: number,
    onEvent: (event: AppEvent, id: string | null) => void,
    signal: AbortSignal,
): Promise<boolean> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
        while (!signal.aborted) {
            const result = await readWithTimeout(reader, idleTimeoutMs);
            if (result.done) {
                buffer += decoder.decode();
                if (buffer.trim()) {
                    if (dispatch(buffer, expectedRunId, onEvent)) {
                        return true;
                    }
                }
                return false;
            }
            buffer += decoder.decode(result.value, { stream: true });
            let boundary = findMessageBoundary(buffer);
            while (boundary >= 0) {
                const block = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + boundaryLength(buffer, boundary));
                if (dispatch(block, expectedRunId, onEvent)) {
                    return true;
                }
                boundary = findMessageBoundary(buffer);
            }
        }
        return false;
    } finally {
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
    }
}

async function readWithTimeout(
    reader: ReadableStreamDefaultReader<Uint8Array>,
    timeoutMs: number,
): Promise<Awaited<ReturnType<typeof reader.read>>> {
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
        return await Promise.race([
            reader.read(),
            new Promise<never>((_resolve, reject) => {
                timeout = setTimeout(
                    () => reject(new ApiClientError("timeout", "이벤트 스트림 응답이 시간 초과되었습니다.")),
                    timeoutMs,
                );
            }),
        ]);
    } finally {
        if (timeout) {
            clearTimeout(timeout);
        }
    }
}

function dispatch(block: string, expectedRunId: RunId, onEvent: (event: AppEvent, id: string | null) => void): boolean {
    const message = parseMessage(block);
    if (message.data.length === 0) {
        return false;
    }
    let payload: unknown;
    try {
        payload = JSON.parse(message.data.join("\n")) as unknown;
    } catch {
        throw new ApiClientError("contract", "호스트가 유효하지 않은 SSE JSON을 보냈습니다.");
    }

    let event: AppEvent;
    try {
        event = parseApiPayload<AppEvent>("appEvent", payload);
    } catch (error) {
        if (error instanceof InvalidApiPayloadError) {
            throw new ApiClientError("contract", "호스트 SSE 이벤트가 API 계약과 일치하지 않습니다.");
        }
        throw error;
    }
    if (event.run_id !== expectedRunId || (message.event && message.event !== event.type)) {
        throw new ApiClientError("contract", "호스트 SSE 이벤트의 실행 범위가 일치하지 않습니다.");
    }
    const isReplayNotice = event.type === "stream.replay_unavailable";
    if (!isReplayNotice && (message.id !== String(event.sequence) || !/^\d+$/.test(message.id ?? ""))) {
        throw new ApiClientError("contract", "호스트 SSE 이벤트 ID와 sequence가 일치하지 않습니다.");
    }
    if (isReplayNotice && message.id !== null) {
        throw new ApiClientError("contract", "replay 만료 안내에는 SSE ID가 없어야 합니다.");
    }
    onEvent(event, isReplayNotice ? null : message.id);
    return event.type === "run.status_changed" && event.payload.terminal !== undefined;
}

function parseMessage(block: string): SseMessage {
    const message: SseMessage = { id: null, event: null, data: [] };
    for (const line of block.split(/\r?\n/)) {
        if (line.startsWith(":")) {
            continue;
        }
        const separator = line.indexOf(":");
        const field = separator < 0 ? line : line.slice(0, separator);
        const value = separator < 0 ? "" : line.slice(separator + 1).replace(/^ /, "");
        switch (field) {
            case "id":
                if (!value.includes("\0")) {
                    message.id = value;
                }
                break;
            case "event":
                message.event = value;
                break;
            case "data":
                message.data.push(value);
                break;
            default:
                break;
        }
    }
    return message;
}

function findMessageBoundary(buffer: string): number {
    return /\r?\n\r?\n/.exec(buffer)?.index ?? -1;
}

function boundaryLength(buffer: string, start: number): number {
    const match = /\r?\n\r?\n/.exec(buffer.slice(start));
    return match?.[0].length ?? 2;
}

function toStatusError(status: number): ApiClientError {
    if (status === 401) {
        return new ApiClientError("unauthorized", "연결 세션이 만료되었습니다. 다시 연결하세요.", status);
    }
    if (status === 403) {
        return new ApiClientError("forbidden", "호스트가 이벤트 연결을 거부했습니다.", status);
    }
    if (status >= 500) {
        return new ApiClientError("server", "호스트 이벤트 연결을 일시적으로 사용할 수 없습니다.", status);
    }
    return new ApiClientError("request", "호스트가 이벤트 연결을 거부했습니다.", status);
}

function normalizeStreamError(error: unknown): ApiClientError {
    if (error instanceof ApiClientError) {
        return error;
    }
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
        return new ApiClientError("timeout", "이벤트 스트림 연결이 시간 초과되었습니다.");
    }
    return new ApiClientError("network", "이벤트 스트림 연결이 끊겼습니다.");
}

function isRetryable(error: ApiClientError): boolean {
    return error.kind === "network" || error.kind === "timeout" || error.kind === "server";
}

function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
    return new Promise((resolve) => {
        const finish = (): void => {
            if (timeout) {
                clearTimeout(timeout);
            }
            signal.removeEventListener("abort", finish);
            resolve();
        };
        const timeout = setTimeout(finish, milliseconds);
        signal.addEventListener("abort", finish, { once: true });
        if (signal.aborted) {
            finish();
        }
    });
}
