/** Validates the visible project registration fields before fixture submission. */
export function isProjectFormValid(displayName: string, rootPath: string): boolean {
    return (
        displayName.trim().length >= 1 &&
        displayName.length <= 120 &&
        rootPath.trim().length >= 1 &&
        rootPath.length <= 4096
    );
}
