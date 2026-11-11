/** Builds a native macOS app for this checkout and Mac; runtime dependencies remain pinned in the checkout. */
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { WORK_ROOT } from "../lib/processes.js";
import { buildIcon, cleanSigningMetadata } from "./buildIcon.js";

if (process.platform !== "darwin") throw new Error("LocalDesk.app requires macOS.");
const contents = join(WORK_ROOT, "dist", "LocalDesk.app", "Contents");
mkdirSync(join(contents, "MacOS"), { recursive: true });
mkdirSync(join(contents, "Resources"), { recursive: true });
buildIcon(WORK_ROOT, contents);
execFileSync(
    "/usr/bin/xcrun",
    [
        "swiftc",
        "-swift-version",
        "5",
        "-O",
        "-module-cache-path",
        join(WORK_ROOT, "dist", "swift-module-cache"),
        "-framework",
        "AppKit",
        "-framework",
        "WebKit",
        join(WORK_ROOT, "scripts", "desktop", "LocalDesk.swift"),
        "-o",
        join(contents, "MacOS", "LocalDesk"),
    ],
    { stdio: "inherit" },
);
writeFileSync(
    join(contents, "Resources", "local-config.json"),
    JSON.stringify({ projectRoot: WORK_ROOT, nodePath: process.execPath, path: process.env.PATH }, null, 4) + "\n",
);
writeFileSync(
    join(contents, "Info.plist"),
    `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>LocalDesk</string>
<key>CFBundleIdentifier</key><string>local.securecode.localdesk</string>
<key>CFBundleName</key><string>LocalDesk</string>
<key>CFBundleDisplayName</key><string>LocalDesk</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleIconFile</key><string>LocalDesk.icns</string>
<key>CFBundleShortVersionString</key><string>1.0.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>\n`,
);
const bundle = join(WORK_ROOT, "dist", "LocalDesk.app");
cleanSigningMetadata(bundle);
execFileSync("/usr/bin/codesign", ["--force", "--sign", "-", bundle], {
    stdio: "inherit",
});
console.log(`Built ${join(WORK_ROOT, "dist", "LocalDesk.app")}`);
