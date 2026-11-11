/** Shared labels for server-confirmed provenance: count modes, pointer selections and answer citations. */
import type { AnswerCitation, PointerSelection } from "@securecode/contracts";

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

export function formatSelection(range: PointerSelection["range"]): string {
    if (range.type === "pdf_page") {
        return `원본 PDF ${range.page}쪽 · byte ${range.start}-${range.end} · parser ${range.parser_version}`;
    }
    return `원본 byte ${range.start}-${range.end}`;
}

/** Symbol citations show file, lines and index revision; pointer citations show the confirmed selection. */
export function formatCitation(citation: AnswerCitation): string {
    if ("location" in citation) {
        const location = citation.location;
        return (
            `${location.relative_path}:${location.start_line}-${location.end_line} · ${location.qualname} · ` +
            `revision ${citation.ref.index_revision} · sha256 ${location.content_sha256.slice(0, 12)}…`
        );
    }
    const { kind, pointer, selection } = citation.ref;
    return `${kind} ${pointer} · revision ${selection.revision} · ${formatSelection(selection.range)}`;
}
