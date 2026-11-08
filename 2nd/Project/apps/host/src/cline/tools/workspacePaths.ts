/**
 * Resolves model-supplied relative paths inside the registered workspace root.
 * Absolute paths, `..`, backslashes, links/junctions on the way and the
 * .git/.securecode directories are refused, so tools cannot leave the workspace
 * or touch repository metadata.
 */
import { lstatSync, mkdirSync, realpathSync, type Stats } from "node:fs";
import { isAbsolute, join, relative, sep } from "node:path";

const BLOCKED_SEGMENTS = new Set([".git", ".securecode"]);
const MAX_RELATIVE_PATH_CHARS = 1024;

export class WorkspacePathError extends Error {
    constructor(message: string) {
        super(message);
        this.name = "WorkspacePathError";
    }
}

function lstatOrNull(path: string): Stats | null {
    try {
        return lstatSync(path);
    } catch {
        return null;
    }
}

function splitRelative(relativePath: string): string[] {
    if (
        relativePath.length === 0 ||
        relativePath.length > MAX_RELATIVE_PATH_CHARS ||
        relativePath.includes("\\") ||
        relativePath.includes("\u0000") ||
        isAbsolute(relativePath) ||
        /^[A-Za-z]:/.test(relativePath)
    ) {
        throw new WorkspacePathError("path must be a relative POSIX path inside the workspace");
    }
    const segments = relativePath.split("/").filter((segment) => segment !== "" && segment !== ".");
    for (const segment of segments) {
        if (segment === ".." || BLOCKED_SEGMENTS.has(segment.toLowerCase())) {
            throw new WorkspacePathError("path leaves the workspace or targets protected metadata");
        }
    }
    return segments;
}

function assertInside(root: string, candidate: string): void {
    const offset = relative(root, candidate);
    if (offset.startsWith("..") || isAbsolute(offset) || offset.split(sep).includes("..")) {
        throw new WorkspacePathError("path resolves outside the workspace");
    }
}

/** Walks existing components and refuses any symbolic link or junction. */
function assertNoLinks(root: string, segments: string[]): void {
    let current = root;
    for (const segment of segments) {
        current = join(current, segment);
        const info = lstatOrNull(current);
        if (!info) return;
        if (info.isSymbolicLink()) throw new WorkspacePathError("links inside the workspace are not followed");
    }
}

export function resolveForRead(root: string, relativePath: string): string {
    const segments = splitRelative(relativePath);
    assertNoLinks(root, segments);
    const target = join(root, ...segments);
    let real: string;
    try {
        real = realpathSync(target);
    } catch {
        throw new WorkspacePathError("file not found");
    }
    assertInside(realpathSync(root), real);
    return real;
}

export function resolveForWrite(root: string, relativePath: string): string {
    const segments = splitRelative(relativePath);
    if (segments.length === 0) throw new WorkspacePathError("a file path is required");
    assertNoLinks(root, segments);
    const target = join(root, ...segments);
    const parent = join(root, ...segments.slice(0, -1));
    mkdirSync(parent, { recursive: true });
    assertInside(realpathSync(root), realpathSync(parent));
    const existing = lstatOrNull(target);
    if (existing && !existing.isFile()) throw new WorkspacePathError("only regular files can be written");
    return target;
}

export function toRelative(root: string, absolute: string): string {
    return relative(root, absolute).split(sep).join("/");
}
