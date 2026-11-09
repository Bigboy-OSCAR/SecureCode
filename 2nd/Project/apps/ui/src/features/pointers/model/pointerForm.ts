/** Validates visible local document paths without checking filesystem access in the browser. */
export function isSourcePathValid(path: string): boolean {
    return path.trim().length > 0 && path.length <= 4096;
}

export function isPdfPathValid(path: string): boolean {
    return isSourcePathValid(path) && path.trim().toLocaleLowerCase().endsWith(".pdf");
}
