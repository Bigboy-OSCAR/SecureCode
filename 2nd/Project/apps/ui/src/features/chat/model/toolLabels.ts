/** Display labels for host tool calls (names from the host tool registry, phases from the run contract). */
import type { ToolCallPhase, ToolCallSummary } from "@securecode/contracts";

const toolNames: Record<string, string> = {
    read_file: "파일 부분 읽기",
    search_file: "파일 검색",
    list_files: "파일 목록",
    write_file: "파일 쓰기",
    run_command: "명령 실행",
    runtime_read: "실행 결과 부분 읽기",
    runtime_search: "실행 결과 검색",
    code_search: "R0 코드 검색",
    code_read: "R0 원문 읽기",
    pdf_parse: "PDF 파싱",
    pdf_status: "PDF 상태 확인",
    pdf_search: "PDF 검색",
    pdf_read_pages: "PDF 페이지 읽기",
};

const phaseNames: Record<ToolCallPhase, string> = {
    requested: "요청됨",
    awaiting_approval: "승인 대기",
    running: "실행 중",
    completed: "완료",
    failed: "실패",
    rejected: "거절됨",
    cancelled: "취소됨",
};

export function toolLabel(name: string): string {
    return toolNames[name] ?? name;
}

export function phaseLabel(phase: ToolCallPhase): string {
    return phaseNames[phase];
}

/** A stored pointer is reported only when the server gave one; a missing size is unknown, never zero. */
export function outputLabel(tool: ToolCallSummary): string {
    const size = tool.output_bytes === undefined ? "크기 미확인" : `${tool.output_bytes.toLocaleString()} bytes`;
    return tool.output_pointer ? `${size} · 실행 결과로 저장됨` : size;
}
