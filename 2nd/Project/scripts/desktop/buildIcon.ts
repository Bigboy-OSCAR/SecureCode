/** Package all macOS icon resolutions from the sidebar's canonical SVG. */
import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";

export function buildIcon(root: string, contents: string): void {
    const executable = join(root, "dist", "build-icon");
    const iconset = join(root, "dist", "LocalDesk.iconset");
    execFileSync(
        "/usr/bin/xcrun",
        [
            "swiftc",
            "-swift-version",
            "5",
            "-module-cache-path",
            join(root, "dist", "swift-module-cache"),
            "-framework",
            "AppKit",
            join(root, "scripts", "desktop", "BuildIcon.swift"),
            "-o",
            executable,
        ],
        { stdio: "inherit" },
    );
    execFileSync(executable, [join(root, "apps", "ui", "public", "brand", "localdesk-mark.svg"), iconset], {
        stdio: "inherit",
    });
    execFileSync(
        "/usr/bin/iconutil",
        ["--convert", "icns", "--output", join(contents, "Resources", "LocalDesk.icns"), iconset],
        { stdio: "inherit" },
    );
}

/** Finder can add signing-incompatible display metadata when an existing local app is rebuilt. */
export function cleanSigningMetadata(bundle: string): void {
    const paths = [bundle, ...readdirSync(bundle, { recursive: true }).map((entry) => join(bundle, String(entry)))];
    for (const path of paths) {
        const attributes = execFileSync("/usr/bin/xattr", [path], { encoding: "utf8" }).trim().split("\n");
        for (const attribute of ["com.apple.FinderInfo", "com.apple.ResourceFork"])
            if (attributes.includes(attribute)) execFileSync("/usr/bin/xattr", ["-d", attribute, path]);
    }
}
