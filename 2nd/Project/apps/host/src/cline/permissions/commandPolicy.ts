/**
 * Commands the host refuses before asking the user. Git commit/push and
 * history-rewriting commands are team-member actions (roadmap header). This
 * static guard recognizes direct commands and common wrappers; it does not
 * inspect executable scripts, repository aliases or arbitrary shell expansion.
 */
// Refusal list (never executed), kept alphabetical.
const GIT_REFUSED_SUBCOMMANDS = new Set(["am", "cherry-pick", "commit", "merge", "push", "rebase", "reset", "tag"]);
const GIT_OPTIONS_WITH_VALUE = new Set(["-C", "-c", "--git-dir", "--work-tree", "--namespace"]);

/** Keeps quoted/escaped words together without evaluating any shell input. */
function commandSegments(command: string): string[][] {
    const segments: string[][] = [];
    let words: string[] = [];
    let word = "";
    let quote = "";
    const finishWord = (): void => {
        if (word) words.push(word);
        word = "";
    };
    for (let index = 0; index < command.length; index += 1) {
        const char = command[index] ?? "";
        const next = command[index + 1] ?? "";
        if (char === "\\" && quote !== "'" && next && !/^[a-z]:/i.test(word)) {
            if (!quote || /["\\$`\n\r]/.test(next)) {
                if (next !== "\n" && next !== "\r") word += next;
                index += 1;
                continue;
            }
        }
        if (quote) {
            if (char === quote) quote = "";
            else word += char;
        } else if (char === '"' || char === "'") {
            quote = char;
        } else if (/[;|&\n\r`()]/.test(char)) {
            finishWord();
            if (words.length) segments.push(words);
            words = [];
        } else if (/\s/.test(char)) {
            finishWord();
        } else {
            word += char;
        }
    }
    finishWord();
    if (words.length) segments.push(words);
    return segments;
}

function programName(word: string): string {
    return word.toLowerCase().split(/[\\/]/).pop() ?? "";
}

/** Remove only common launch wrappers; unknown programs remain opaque. */
function unwrapCommand(words: string[]): string[] {
    let index = 0;
    while (index < words.length) {
        const word = words[index] ?? "";
        if (/^[a-z_][a-z0-9_]*=/i.test(word)) {
            index += 1;
        } else if (["env", "command", "exec", "sudo"].includes(programName(word))) {
            const wrapper = programName(word);
            index += 1;
            while ((words[index] ?? "").startsWith("-")) {
                const option = words[index] ?? "";
                index += 1;
                if (
                    (wrapper === "env" && ["-u", "--unset", "-C", "--chdir"].includes(option)) ||
                    (wrapper === "sudo" && ["-u", "-g", "-h", "-p", "-C", "-T"].includes(option))
                )
                    index += 1;
                if (option === "--") break;
            }
        } else {
            break;
        }
    }
    return words.slice(index);
}

function gitSubcommand(words: string[]): string | null {
    const base = programName(words[0] ?? "");
    if (base !== "git" && base !== "git.exe") return null;
    for (let index = 1; index < words.length; index += 1) {
        const word = words[index] ?? "";
        if (GIT_OPTIONS_WITH_VALUE.has(word)) {
            index += 1;
            continue;
        }
        if (word.startsWith("-")) continue;
        return word.toLowerCase();
    }
    return null;
}

/** Returns a refusal reason, or null when the command may be offered for approval. */
export function refuseCommand(command: string): string | null {
    for (const segment of commandSegments(command)) {
        const words = unwrapCommand(segment);
        const program = programName(words[0] ?? "");
        if (["sh", "bash", "zsh", "dash", "ksh", "cmd", "cmd.exe"].includes(program)) {
            const option = words.findIndex((word) => /^-[a-z]*c[a-z]*$/i.test(word) || /^\/c$/i.test(word));
            if (option >= 1) {
                const refusal = refuseCommand(words.slice(option + 1).join(" "));
                if (refusal) return refusal;
            }
        }
        if (
            ["git", "git.exe"].includes(program) &&
            words.slice(1).some((word) => /^(?:-c|--config-env=)?alias\./i.test(word))
        )
            return "Git alias overrides are not supported by the SecureCode command guard";
        const subcommand = gitSubcommand(words);
        if (subcommand && GIT_REFUSED_SUBCOMMANDS.has(subcommand)) {
            return `git ${subcommand} is reserved for team members and is never run by SecureCode`;
        }
    }
    return null;
}
