/** Render common answer formatting without interpreting model HTML, scripts, or remote images. */
import { CopyAnswer } from "./CopyAnswer.js";
import type { ReactNode } from "react";
function inline(text: string): ReactNode[] {
    return text
        .split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g)
        .map((part, index) =>
            part.startsWith("`") && part.endsWith("`") ? (
                <code key={index}>{part.slice(1, -1)}</code>
            ) : part.startsWith("**") && part.endsWith("**") ? (
                <strong key={index}>{part.slice(2, -2)}</strong>
            ) : (
                part
            ),
        );
}
export function AnswerText({ text }: { text: string }): React.JSX.Element {
    const blocks = text.split(/(```[^\n]*\n[\s\S]*?(?:```|$))/g);
    return (
        <div className="answer-text">
            {blocks.map((block, index) => {
                if (block.startsWith("```")) {
                    const firstBreak = block.indexOf("\n");
                    const language = block.slice(3, firstBreak).trim();
                    const code = block.slice(firstBreak + 1).replace(/```$/, "");
                    return (
                        <div className="desk-answer-code" key={index}>
                            <div className="desk-code-header">
                                <span>{language || "CODE"}</span>
                                <CopyAnswer text={code} label="코드 복사" />
                            </div>
                            <pre>
                                <code>{code}</code>
                            </pre>
                        </div>
                    );
                }
                return (
                    <div key={index}>
                        {block.split("\n").map((line, lineIndex) => {
                            const heading = line.match(/^#{1,4}\s+(.+)/);
                            if (heading) return <h4 key={lineIndex}>{inline(heading[1] ?? "")}</h4>;
                            const bullet = line.match(/^(?:[-*]|\d+\.)\s+(.+)/);
                            if (bullet)
                                return (
                                    <p className="desk-answer-bullet" key={lineIndex}>
                                        • {inline(bullet[1] ?? "")}
                                    </p>
                                );
                            return <p key={lineIndex}>{line ? inline(line) : <br />}</p>;
                        })}
                    </div>
                );
            })}
        </div>
    );
}
