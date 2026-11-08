/** Renders question entry, answer stream, run history, and cancellation intent. */
import { useState, type FormEvent } from "react";
import { Alert, Button, InputField, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";

const toolLabels: Record<string, string> = {
    read_log: "로그 읽기",
    run_project_command: "프로젝트 명령 실행",
};

export function ConversationPanel(): React.JSX.Element {
    const [prompt, setPrompt] = useState("");
    const [sent, setSent] = useState(false);
    const [cancelRequested, setCancelRequested] = useState(false);
    const activeRun = fixtureAdapter.runs[0]!;
    const completedRun = fixtureAdapter.runs[1]!;
    const streamEvent = fixtureAdapter.outputDelta;
    const streamText = streamEvent.type === "run.output_delta" ? streamEvent.payload.text : "";

    function handleSubmit(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault();
        if (prompt.trim().length > 0) {
            setSent(true);
        }
    }

    return (
        <section className="feature-card" aria-labelledby="conversation-heading" data-testid="screen-chat">
            <div className="feature-heading">
                <h2 id="conversation-heading">대화 · 실행 이력</h2>
                <StatusBadge
                    label={activeRun.status === "awaiting_approval" ? "승인 대기 중" : activeRun.status}
                    tone="warning"
                />
            </div>
            <p>
                세션 {activeRun.session_id} · 실행 {activeRun.run_id} · 이력 {fixtureAdapter.runList.items.length}건
            </p>
            <article className="message-card">
                <h3>질문</h3>
                <p>{activeRun.prompt_preview}</p>
            </article>
            <article className="message-card" aria-live="polite">
                <h3>답변 스트림 예시</h3>
                <p>{boundedPreview(streamText, 280)}</p>
            </article>
            <div className="tool-history">
                <h3>실행 도구 이력</h3>
                {activeRun.tool_calls.map((tool) => (
                    <div className="tool-row" key={tool.tool_call_id}>
                        <strong>{toolLabels[tool.tool_name] ?? "작업 도구"}</strong>
                        <span>{tool.summary}</span>
                        <span>{tool.output_bytes?.toLocaleString() ?? 0} bytes 저장</span>
                    </div>
                ))}
                {activeRun.tool_calls_truncated ? <p>도구 이력 일부만 표시됩니다.</p> : null}
            </div>
            <Button
                type="button"
                disabled={cancelRequested}
                onClick={() => setCancelRequested(true)}
                data-testid="run-cancel"
            >
                취소 요청
            </Button>
            {cancelRequested ? (
                <Alert title="취소 결과 확인이 필요합니다" variant="warning">
                    서버가 종료를 확인하기 전까지 실행 상태를 확정하지 않습니다. 이 화면에서는 실제 요청을 보내지
                    않았습니다.
                </Alert>
            ) : null}
            <form onSubmit={handleSubmit} className="stack-form">
                <InputField
                    id="question-input"
                    label="질문 입력"
                    value={prompt}
                    maxLength={32000}
                    onChange={(event) => {
                        setPrompt(event.currentTarget.value);
                        setSent(false);
                    }}
                    data-testid="question-input"
                />
                <Button
                    type="submit"
                    variant="primary"
                    disabled={prompt.trim().length === 0}
                    data-testid="question-submit"
                >
                    질문 예시 표시
                </Button>
            </form>
            {sent ? <p role="status">질문 입력을 확인했습니다. 실제 실행 요청은 보내지 않았습니다.</p> : null}
            <details>
                <summary>빈 대화 상태</summary>
                <p>질문을 입력해 시작하세요.</p>
            </details>
            <details>
                <summary>실행 대기·오류·무결과 예시</summary>
                <p>답변을 받는 중… {boundedPreview(streamText, 280)}</p>
                <Alert title="현재 실행 중인 작업이 있습니다" variant="warning">
                    {fixtureAdapter.runAlreadyActive.error.message}
                </Alert>
                {fixtureAdapter.symbolNoMatch.no_match ? (
                    <Alert title="관련 코드 근거를 찾지 못했습니다" variant="info">
                        질문에 식별자나 파일 이름을 포함해 다시 요청하세요.
                    </Alert>
                ) : null}
            </details>
            <details>
                <summary>완료·취소된 실행 예시</summary>
                <p>
                    {completedRun.terminal?.status ?? completedRun.status} ·{" "}
                    {completedRun.answer.truncated ? "일부 표시" : "답변 완료"}
                </p>
                <p>{fixtureAdapter.runs[2]!.terminal?.status ?? fixtureAdapter.runs[2]!.status}</p>
            </details>
        </section>
    );
}
