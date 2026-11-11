export function selectorLabel(selector: string): string {
    const labels: Record<string, string> = {
        byte: "바이트 범위",
        json_path: "JSON 경로",
        line: "줄 범위",
        pdf_page: "PDF 페이지",
        section: "문서 구역",
    };
    return labels[selector] ?? selector;
}

export function isNumericSelector(kind: string): boolean {
    return kind === "byte" || kind === "line" || kind === "pdf_page";
}

export function formatSelection(
    range:
        | { type: string; start: number; end: number }
        | { type: string; page: number; start: number; end: number; parser_version?: string },
): string {
    if (range.type === "pdf_page" && "page" in range) {
        return `원본 PDF ${range.page}쪽 · byte ${range.start}-${range.end}${range.parser_version ? ` · parser ${range.parser_version}` : ""}`;
    }
    return `${range.type} byte ${range.start}-${range.end}`;
}

export function countModeLabel(mode: string): string {
    switch (mode) {
        case "exact":
            return "정확 계수";
        case "provider_estimate":
            return "제공자 추정";
        case "provider_reported":
            return "제공자 실측";
        default:
            return mode;
    }
}

export function formatRequestedRange(kind: string, start: string, end: string, value: string): string {
    if (kind === "line" || kind === "pdf_page" || kind === "byte") {
        return `${kind} ${start}${end ? `-${end}` : ""}`;
    }
    return `${kind} ${value}`;
}
