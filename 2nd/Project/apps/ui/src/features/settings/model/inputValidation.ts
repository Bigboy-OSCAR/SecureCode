/** Keeps local fixture forms aligned with the public request constraints. */
export function isBootstrapCodeValid(code: string): boolean {
    return /^[A-Za-z0-9-]{8,64}$/.test(code);
}
