/** Builds a read selector from the range form and explains an unusable range (1.6). */
import type { PointerReadRequest } from "@securecode/contracts";

type PointerSelector = NonNullable<PointerReadRequest["selector"]>;
export type SelectorKind = PointerSelector["type"];

export function buildSelector(
    kind: SelectorKind,
    start: string,
    end: string,
    value: string,
): PointerSelector | undefined {
    switch (kind) {
        case "line":
        case "pdf_page":
        case "byte": {
            const first = Number(start);
            const last = end ? Number(end) : undefined;
            if (!Number.isInteger(first) || first < (kind === "byte" ? 0 : 1)) {
                return undefined;
            }
            if (last !== undefined && (!Number.isInteger(last) || last < first)) {
                return undefined;
            }
            return {
                type: kind,
                start: first,
                ...(last === undefined ? {} : { end: last }),
            };
        }
        case "section":
            return value.trim() ? { type: kind, section: value.trim() } : undefined;
        case "json_path":
            return value.trim() ? { type: kind, path: value.trim() } : undefined;
    }
}

/** Says which part of the requested range is wrong, instead of one generic message. */
export function rangeProblem(kind: SelectorKind, start: string): string {
    if (kind === "section" || kind === "json_path") {
        return "읽을 구역 이름이나 JSON 경로를 입력하세요.";
    }
    // Korean particles differ by the final consonant of the unit (줄 → 을/은, 페이지·바이트 → 를/는).
    const [unit, object, topic] =
        kind === "pdf_page" ? ["페이지", "를", "는"] : kind === "byte" ? ["바이트", "를", "는"] : ["줄", "을", "은"];
    const first = Number(start);
    if (!start.trim() || !Number.isInteger(first) || first < (kind === "byte" ? 0 : 1)) {
        return `시작 ${unit}${object} ${kind === "byte" ? "0" : "1"} 이상의 정수로 입력하세요.`;
    }
    return `끝 ${unit}${topic} 시작 ${unit}(${first})보다 작을 수 없습니다.`;
}
