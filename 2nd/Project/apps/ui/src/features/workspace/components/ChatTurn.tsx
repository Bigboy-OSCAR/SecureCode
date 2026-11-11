import type { RunSnapshot } from "@securecode/contracts";
import { BrandMark } from "../../../components/BrandMark.js";
import { AnswerView } from "../../chat/components/AnswerView.js";
import { ToolHistory } from "../../chat/components/ToolHistory.js";

/** Keep each question, its activity, and its answer together, including restored turns. */
export function ChatTurn({ run, current = false }: { run: RunSnapshot; current?: boolean }): React.JSX.Element {
    return (
        <article
            className="desk-turn"
            data-testid="conversation-turn"
            data-run-id={run.run_id}
            aria-label="질문과 답변"
        >
            {current ? <p className="desk-date">{new Date(run.created_at).toLocaleDateString("ko-KR")}</p> : null}
            <div className="desk-user-message">{run.prompt_preview}</div>
            <div className="desk-response-title">
                <span>
                    <BrandMark compact />
                </span>
                <strong>LocalDesk</strong>
                <small>로컬</small>
            </div>
            <ToolHistory run={run} current={current} />
            <AnswerView run={run} />
        </article>
    );
}
