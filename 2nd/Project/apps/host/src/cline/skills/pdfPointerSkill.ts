/**
 * Explicit export of skills/pdf-pointer/SKILL.md for the app's SDK prompt (4.9). The SDK does not load
 * skill files by itself (configExtensions are off, 3.1 C-02); the host reads this file, checks that the
 * tools it documents are exactly the app-owned PDF tool registry, and appends it to the system prompt.
 * skills/pdf-pointer/registration.json is the fixture 3.6 compares against when it registers the tools.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { PDF_TOOL_NAMES } from "../tools/pdfTools.js";

export const PDF_POINTER_SKILL_FILE = "skills/pdf-pointer/SKILL.md";

export interface LoadedSkill {
    id: string;
    version: string;
    sha256: string;
    tools: string[];
    /** Text appended to the system prompt; the SKILL.md body without its front matter. */
    promptSection: string;
}

function frontMatter(source: string): { fields: Map<string, string>; body: string } {
    const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(source);
    if (!match?.[1]) throw new Error("SKILL.md has no front matter");
    const fields = new Map<string, string>();
    for (const line of match[1].split(/\r?\n/)) {
        const at = line.indexOf(":");
        if (at > 0) fields.set(line.slice(0, at).trim(), line.slice(at + 1).trim());
    }
    return { fields, body: source.slice(match[0].length).trim() };
}

/** Tool names in the first column of the "## 도구" table. */
export function documentedTools(body: string): string[] {
    const section = /^## 도구\s*$([\s\S]*?)(?=^## )/m.exec(body)?.[1] ?? "";
    return [...section.matchAll(/^\| `([a-z_]+)` \|/gm)].map((match) => match[1] ?? "");
}

export function loadPdfPointerSkill(workRoot: string): LoadedSkill {
    const raw = readFileSync(join(workRoot, PDF_POINTER_SKILL_FILE));
    const { fields, body } = frontMatter(raw.toString("utf8"));
    const id = fields.get("name");
    const version = fields.get("version");
    if (id !== "pdf-pointer" || !version) throw new Error("SKILL.md front matter must name pdf-pointer and a version");
    const tools = documentedTools(body);
    const registry = [...PDF_TOOL_NAMES];
    if (tools.length !== registry.length || registry.some((name) => !tools.includes(name))) {
        throw new Error(`SKILL.md tools [${tools.join(", ")}] do not match the PDF tool registry`);
    }
    const sha256 = createHash("sha256").update(raw).digest("hex");
    const promptSection = `<skill name="${id}" version="${version}">\n${body}\n</skill>`;
    return { id, version, sha256, tools: registry, promptSection };
}

/** System prompt with the given skills appended, in order. */
export function withSkills(systemPrompt: string, skills: readonly LoadedSkill[]): string {
    return [systemPrompt, ...skills.map((skill) => skill.promptSection)].join("\n\n");
}
