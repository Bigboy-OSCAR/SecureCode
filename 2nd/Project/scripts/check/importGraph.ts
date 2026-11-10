/**
 * Runtime import graph of the product sources and its cycles (3.7 structure check).
 * TypeScript: relative value imports/exports (`import type` is erased and ignored).
 * Python: module-level `securecode_context` imports (indented imports are lazy and cannot form a load cycle).
 */
import { existsSync } from "node:fs";
import { dirname, join, normalize } from "node:path";
import type { FileUnderCheck } from "./structureRules.js";

const TS_ROOTS = /^(apps\/[^/]+\/src|contracts\/src|tools\/[^/]+\/src|scripts)\/.*\.tsx?$/;
const PY_ROOT = "services/context-service/src/";
const TS_IMPORT = /^\s*(?:import|export)\s+(?!type\b)(?:[^'"]*?\sfrom\s+)?["'](\.{1,2}\/[^"']+)["']/gm;
const PY_IMPORT =
    /^(?:from\s+(\.+[\w.]*|securecode_context[\w.]*)\s+import\s+(\([^)]*\)|[^\n#]+)|import\s+(securecode_context[\w.]*))/gm;

function tsTarget(from: string, specifier: string, workRoot: string): string | undefined {
    const base = normalize(join(dirname(from), specifier)).replaceAll("\\", "/");
    const stem = base.replace(/\.js$/, "");
    for (const candidate of [`${stem}.ts`, `${stem}.tsx`, `${stem}/index.ts`, `${stem}/index.tsx`]) {
        if (existsSync(join(workRoot, candidate))) return candidate;
    }
    return undefined;
}

function pyModuleFile(module: string, workRoot: string): string | undefined {
    const base = PY_ROOT + module.replaceAll(".", "/");
    for (const candidate of [`${base}.py`, `${base}/__init__.py`]) {
        if (existsSync(join(workRoot, candidate))) return candidate;
    }
    return undefined;
}

function pyAbsolute(from: string, module: string): string {
    if (!module.startsWith(".")) return module;
    const dots = /^\.+/.exec(module)?.[0].length ?? 0;
    const parts = from.slice(PY_ROOT.length).replace(/\.py$/, "").split("/");
    // The importing file's package (for __init__.py, the package itself), then one level up per extra dot.
    const packageParts = parts.slice(0, parts.length - dots);
    const rest = module.slice(dots);
    return [...packageParts, ...(rest ? [rest] : [])].join(".");
}

function pyTargets(file: FileUnderCheck, workRoot: string): string[] {
    const targets: string[] = [];
    // Drop `if TYPE_CHECKING:` blocks: those imports never run.
    const text = file.text.replace(/^if TYPE_CHECKING:\n(?:[ \t]+[^\n]*\n|\n)*/gm, "");
    for (const match of text.matchAll(PY_IMPORT)) {
        const module = pyAbsolute(file.path, match[1] ?? match[3] ?? "");
        const own = pyModuleFile(module, workRoot);
        if (own) targets.push(own);
        for (const name of (match[2] ?? "").replace(/[()]/g, "").split(",")) {
            const sub = pyModuleFile(`${module}.${name.trim().split(/\s+/)[0] ?? ""}`, workRoot);
            if (sub) targets.push(sub);
        }
    }
    return targets;
}

export function importEdges(files: readonly FileUnderCheck[], workRoot: string): Map<string, string[]> {
    const edges = new Map<string, string[]>();
    for (const file of files) {
        if (TS_ROOTS.test(file.path) && !/\.test\.tsx?$/.test(file.path)) {
            const targets = [...file.text.matchAll(TS_IMPORT)]
                .map((match) => tsTarget(file.path, match[1] ?? "", workRoot))
                .filter((target): target is string => target !== undefined);
            edges.set(file.path, targets);
        } else if (file.path.startsWith(PY_ROOT) && file.path.endsWith(".py")) {
            edges.set(file.path, pyTargets(file, workRoot));
        }
    }
    return edges;
}

/** Strongly connected components with more than one file (or a self-import): each is one import cycle. */
export function findCycles(edges: Map<string, string[]>): string[][] {
    let counter = 0;
    const index = new Map<string, number>();
    const low = new Map<string, number>();
    const stack: string[] = [];
    const onStack = new Set<string>();
    const cycles: string[][] = [];
    const visit = (node: string): void => {
        index.set(node, counter);
        low.set(node, counter++);
        stack.push(node);
        onStack.add(node);
        for (const next of edges.get(node) ?? []) {
            if (!edges.has(next)) continue;
            if (!index.has(next)) {
                visit(next);
                low.set(node, Math.min(low.get(node) ?? 0, low.get(next) ?? 0));
            } else if (onStack.has(next)) low.set(node, Math.min(low.get(node) ?? 0, index.get(next) ?? 0));
        }
        if (low.get(node) !== index.get(node)) return;
        const component: string[] = [];
        let member: string | undefined;
        do {
            member = stack.pop();
            if (member === undefined) break;
            onStack.delete(member);
            component.push(member);
        } while (member !== node);
        if (component.length > 1 || (edges.get(node) ?? []).includes(node)) cycles.push(component.sort());
    };
    for (const node of edges.keys()) if (!index.has(node)) visit(node);
    return cycles;
}
