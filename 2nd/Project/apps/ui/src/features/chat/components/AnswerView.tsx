import { useEffect, useState } from "react";
import type { RunSnapshot } from "@securecode/contracts";
import { Button } from "../../../components/index.js";
import { formatCitation } from "../../shared/model/provenanceLabels.js";

/** Rendered answer characters per step: bounded DOM, but nothing is hidden without saying so. */
export const ANSWER_STEP_CHARS = 4000;

interface AnswerViewProps {
    run: RunSnapshot | null;
}

export function AnswerView({ run }: AnswerViewProps): React.JSX.Element {
    const [visible, setVisible] = useState(ANSWER_STEP_CHARS);
    const runId = run?.run_id ?? null;
    useEffect(() => setVisible(ANSWER_STEP_CHARS), [runId]);

    if (!run) {
        return (
            <article className="message-card">
                <h3>답변</h3>
                <p>답변이 도착하면 여기에 표시됩니다.</p>
            </article>
        );
    }
    const text = run.answer.text;
    const hidden = Math.max(0, text.length - visible);
    const stopped = run.status === "failed" || run.status === "cancelled";
    const terminal = run.status === "completed" || stopped;
    const citations = run.answer.citations ?? [];

    return (
        <article className="message-card" data-testid="answer">
            <h3>{stopped ? "답변 (중단 전 결과)" : "답변"}</h3>
            {text.length > 0 ? <p className="answer-text">{text.slice(0, visible)}</p> : null}
            {hidden > 0 ? (
                <Button type="button" onClick={() => setVisible((current) => current + ANSWER_STEP_CHARS)}>
                    답변 더 보기 ({hidden.toLocaleString()}자 남음)
                </Button>
            ) : null}
            {run.answer.truncated ? <p>호스트가 답변의 일부만 보관했습니다. 나머지는 표시할 수 없습니다.</p> : null}
            {terminal && text.length === 0 ? <p>표시할 답변이 없습니다.</p> : null}
            {terminal ? (
                <div data-testid="answer-citations">
                    <h4>답변에 사용한 근거</h4>
                    {citations.length === 0 ? (
                        <p>서버가 확인한 근거가 없습니다. 답변의 출처를 단정하지 마세요.</p>
                    ) : (
                        <ul className="compact-list">
                            {citations.map((citation, index) => (
                                <li key={`${citation.ref.kind}-${index}`}>{formatCitation(citation)}</li>
                            ))}
                        </ul>
                    )}
                    {run.answer.citations_page?.has_more ? <p>근거 목록 일부만 표시됩니다.</p> : null}
                </div>
            ) : null}
        </article>
    );
}
