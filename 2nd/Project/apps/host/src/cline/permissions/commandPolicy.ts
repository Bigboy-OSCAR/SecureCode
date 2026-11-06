/**
 * Commands the host refuses before asking the user. Git commit/push and
 * history-rewriting commands are team-member actions (roadmap header), so the
 * project command tool never runs them, even when a user would approve.
 */
// Refusal list (never executed), kept alphabetical.
const GIT_REFUSED_SUBCOMMANDS = new Set(["am", "cherry-pick", "commit", "merge", "push", "rebase", "reset", "tag"]);
const GIT_OPTIONS_WITH_VALUE = new Set(["-C", "-c", "--git-dir", "--work-tree", "--namespace"]);

/** Splits on shell separators so `a && git push` is checked segment by segment. */
function commandSegments(command: string): string[][] {
    return command
        .split(/&&|\|\||[;|&\n\r`]|\$\(/)
        .map((segment) => segment.trim().split(/\s+/).filter(Boolean))
        .filter((words) => words.length > 0);
}

function gitSubcommand(words: string[]): string | null {
    const program = (words[0] ?? "").replace(/^["']|["']$/g, "").toLowerCase();
    const base = program.split(/[\\/]/).pop() ?? "";
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
    for (const words of commandSegments(command)) {
        const subcommand = gitSubcommand(words);
        if (subcommand && GIT_REFUSED_SUBCOMMANDS.has(subcommand)) {
            return `git ${subcommand} is reserved for team members and is never run by SecureCode`;
        }
    }
    return null;
}
