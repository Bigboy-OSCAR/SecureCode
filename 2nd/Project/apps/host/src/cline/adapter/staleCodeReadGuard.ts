/** Stop a repeated stale indexed read, while leaving its first failure open to recovery. */
import { turnStorage } from "./turnContext.js";

export const STALE_CODE_READ_GUIDANCE =
    "SOURCE_CHANGED: The indexed file has changed. Repeating code_search does not refresh the index. " +
    "Use read_file for the current file contents, or ask the user to run 인덱스 생성·갱신 before trying code_read again.";

export const STALE_CODE_READ_STOP_MESSAGE =
    "원본 파일이 색인 이후 변경되어 같은 코드 읽기가 반복되었습니다. " +
    "왼쪽의 ‘인덱스 생성·갱신’에서 해당 프로젝트를 갱신한 뒤 다시 질문하세요. " +
    "현재 파일 내용만 필요하면 파일을 직접 읽어 달라고 요청할 수 있습니다.";

/** Called only for a typed SOURCE_CHANGED response from an actual code_read. */
export function recordStaleCodeRead(candidateId: string, revision: number, toolCallId?: string): void {
    const turn = turnStorage.getStore();
    if (!turn) return;
    const failures = (turn.staleCodeReads ??= new Map<string, number>());
    const key = JSON.stringify([candidateId, revision]);
    const count = (failures.get(key) ?? 0) + 1;
    failures.set(key, count);
    // The SDK supplies the call id. Direct tool invocations outside the SDK must not stop another call.
    if (count >= 2 && toolCallId) (turn.staleCodeReadStops ??= new Set()).add(toolCallId);
}
