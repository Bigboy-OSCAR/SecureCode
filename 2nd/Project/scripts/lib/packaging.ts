/**
 * Local packaging check for `npm run build` (3.7): the built UI and the context-service wheel must be
 * complete and match the lockfiles, then a release manifest with versions and SHA-256 hashes is written to
 * dist/securecode-local/manifest.json (git-ignored). Nothing is uploaded or deployed.
 */
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SERVICE_DIR, WORK_ROOT } from "./processes.js";
import type { StepResult } from "./report.js";

const sha256 = (path: string): string => createHash("sha256").update(readFileSync(path)).digest("hex");
const readJson = (path: string): Record<string, unknown> =>
    JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;

function uiArtifacts(): { files: Record<string, string>; problem?: string } {
    const dist = join(WORK_ROOT, "apps", "ui", "dist");
    let index: string;
    try {
        index = readFileSync(join(dist, "index.html"), "utf8");
    } catch {
        return { files: {}, problem: "apps/ui/dist/index.html missing" };
    }
    const files: Record<string, string> = {};
    for (const [, asset] of index.matchAll(/(?:src|href)="\/(assets\/[^"]+)"/g)) {
        try {
            files[asset ?? ""] = sha256(join(dist, asset ?? ""));
        } catch {
            return { files, problem: `index.html references missing ${asset}` };
        }
    }
    if (!Object.keys(files).some((name) => name.endsWith(".js"))) return { files, problem: "no UI script bundle" };
    return { files };
}

function newestWheel(): string | undefined {
    const dist = join(SERVICE_DIR, "dist");
    const wheels = readdirSync(dist, { withFileTypes: true })
        .filter((entry) => entry.isFile() && entry.name.endsWith(".whl"))
        .map((entry) => join(dist, entry.name));
    return wheels.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)[0];
}

/** Lists the wheel with the service's own interpreter (isolated mode) and checks the entry modules. */
function wheelProblem(wheel: string): string | undefined {
    const python = join(SERVICE_DIR, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
    const script = "import sys,zipfile;print('\\n'.join(zipfile.ZipFile(sys.argv[1]).namelist()))";
    const listing = spawnSync(python, ["-I", "-c", script, wheel], { encoding: "utf8" });
    if (listing.status !== 0) return "cannot read the wheel";
    for (const required of ["securecode_context/app/__main__.py", "securecode_context/symbols/__main__.py"]) {
        if (!listing.stdout.split(/\r?\n/).includes(required)) return `wheel lacks ${required}`;
    }
    return undefined;
}

function lockedVersions(): Record<string, string> {
    const lock = readJson(join(WORK_ROOT, "package-lock.json")) as { packages?: Record<string, { version?: string }> };
    const pick = (name: string): string => lock.packages?.[`node_modules/${name}`]?.version ?? "missing";
    return {
        "@cline/sdk": pick("@cline/sdk"),
        react: pick("react"),
        vite: pick("vite"),
        typescript: pick("typescript"),
    };
}

export function packagingSteps(): Promise<StepResult[]> {
    const ui = uiArtifacts();
    let wheel: string | undefined;
    try {
        wheel = newestWheel();
    } catch {
        wheel = undefined;
    }
    const problem =
        ui.problem ?? (wheel ? wheelProblem(wheel) : "no context-service wheel in services/context-service/dist");
    if (problem || !wheel) {
        return Promise.resolve([{ name: "package: local release manifest", status: "FAIL", detail: problem ?? "" }]);
    }
    const rootPackage = readJson(join(WORK_ROOT, "package.json")) as { engines?: { node?: string } };
    const manifest = {
        schema_version: "1",
        built_at: new Date().toISOString(),
        node: { running: process.version, engines: rootPackage.engines?.node ?? "" },
        python: {
            requires: /requires-python\s*=\s*"([^"]+)"/.exec(
                readFileSync(join(SERVICE_DIR, "pyproject.toml"), "utf8"),
            )?.[1],
        },
        locked: lockedVersions(),
        lockfiles: {
            "package-lock.json": sha256(join(WORK_ROOT, "package-lock.json")),
            "uv.lock": sha256(join(SERVICE_DIR, "uv.lock")),
        },
        context_service_wheel: { file: wheel.split(/[\\/]/).at(-1), sha256: sha256(wheel) },
        ui_assets: ui.files,
    };
    const out = join(WORK_ROOT, "dist", "securecode-local");
    mkdirSync(out, { recursive: true });
    writeFileSync(join(out, "manifest.json"), JSON.stringify(manifest, null, 4) + "\n");
    const detail = `dist/securecode-local/manifest.json (${manifest.context_service_wheel.file}, ${Object.keys(ui.files).length} UI assets)`;
    return Promise.resolve([{ name: "package: local release manifest", status: "PASS", detail }]);
}
