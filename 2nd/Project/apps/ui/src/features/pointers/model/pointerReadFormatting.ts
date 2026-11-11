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

export function formatRequestedRange(kind: string, start: string, end: string, value: string): string {
    if (kind === "line" || kind === "pdf_page" || kind === "byte") {
        return `${kind} ${start}${end ? `-${end}` : ""}`;
    }
    return `${kind} ${value}`;
}
