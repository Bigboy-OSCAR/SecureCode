/** Validates visible local document paths without checking filesystem access in the browser. */
export function isSourcePathValid(path: string): boolean {
    return path.trim().length > 0 && path.length <= 4096;
}
