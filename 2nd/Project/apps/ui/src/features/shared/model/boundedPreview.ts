/** Caps rendered source text so an unbounded fixture never enters the UI DOM. */
export function boundedPreview(text: string, limit: number): string {
    if (text.length <= limit) {
        return text;
    }
    return `${text.slice(0, limit)}…`;
}
