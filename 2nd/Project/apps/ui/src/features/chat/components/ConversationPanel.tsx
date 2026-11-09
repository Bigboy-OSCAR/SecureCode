import { Alert, Button, StatusBadge, TextAreaField } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";
import { useConversationActions } from "../hooks/useConversationActions.js";
import type { RunController } from "../model/runController.js";
import type { RunViewState } from "../model/runState.js";

const toolLabels: Record<string, string> = {
    read_log: "로그 읽기",
    run_project_command: "프로젝트 명령 실행",
};

const statusLabels = {
    queued: "실행 대기 중",
    running: "실행 중",
    awaiting_approval: "승인 대기 중",
    cancelling: "취소 요청 중",
    completed: "완료",
    failed: "실패",
    cancelled: "취소됨",
} as const;

export interface ConversationPanelProps {
    controller: RunController;
    state: RunViewState;
}

export function ConversationPanel({ controller, state }: ConversationPanelProps): React.JSX.Element {
    const actions = useConversationActions(controller, state);
    const run = state.snapshot;
    const runCanContinue = !run || run.status === "completed" || run.status === "failed" || run.status === "cancelled";
    const displayRun = run ?? fixtureAdapter.runs[0]!;
    const streamText =
        run?.answer.text ??
        (fixtureAdapter.outputDelta.type === "run.output_delta" ? fixtureAdapter.outputDelta.payload.text : "");
    const currentStatus = run ? statusLabels[run.status] : "질문을 입력해 시작하세요";
    const operationLabel =
        state.operation?.kind === "cancelling"
            ? "취소 결과 확인 중…"
            : state.operation?.kind === "creating"
              ? "실행을 확인하는 중…"
              : null;

    return (
        <section
            id="screen-chat"
            className="feature-card"
            aria-labelledby="conversation-heading"
            data-testid="screen-chat"
        >
            <div className="feature-heading">
                <h2 id="conversation-heading">대화 · 실행 이력</h2>
                <StatusBadge label={currentStatus} tone={run ? "warning" : "neutral"} />
            </div>
            {run ? (
                <p>
                    세션 {run.session_id} · 실행 {run.run_id} · 이력 {fixtureAdapter.runList.items.length}건
                </p>
            ) : (
                <p>질문을 입력해 fixture 실행 동작을 확인하세요. 실제 API 요청은 보내지 않습니다.</p>
            )}
            {state.connection === "disconnected" ? (
                <Alert title="연결이 끊겼습니다" variant="warning">
                    작업은 계속될 수 있습니다. 기존 입력과 결과는 유지됩니다.
                    <Button type="button" onClick={actions.reconnect} data-testid="run-reconnect">
                        최신 상태 다시 확인
                    </Button>
                </Alert>
            ) : null}
            {state.connection === "recovering" ? <p role="status">최신 실행 상태를 확인하는 중…</p> : null}
            {state.error ? (
                <Alert title="실행 상태를 확인하세요" variant="error">
                    {state.error}
                </Alert>
            ) : null}
            {operationLabel ? <p role="status">{operationLabel}</p> : null}
            <article className="message-card">
                <h3>질문</h3>
                <p>{run?.prompt_preview ?? "질문이 아직 없습니다."}</p>
            </article>
            <article className="message-card" aria-live="polite">
                <h3>답변</h3>
                <p>{run ? boundedPreview(streamText, 280) : "답변이 도착하면 여기에 표시됩니다."}</p>
                {run?.status === "failed" || run?.status === "cancelled" ? (
                    <p>중단 전 결과: {boundedPreview(streamText, 280)}</p>
                ) : null}
                {run?.answer.truncated ? <p>답변 일부만 표시됩니다.</p> : null}
                {run && isTerminalWithoutAnswer(run) ? <p>표시할 답변이 없습니다.</p> : null}
            </article>
            <div className="tool-history">
                <h3>실행 도구 이력</h3>
                {displayRun.tool_calls.map((tool) => (
                    <div className="tool-row" key={tool.tool_call_id}>
                        <strong>{toolLabels[tool.tool_name] ?? "작업 도구"}</strong>
                        <span>{tool.summary}</span>
                        <span>{tool.output_bytes?.toLocaleString() ?? 0} bytes 저장</span>
                    </div>
                ))}
                {displayRun.tool_calls_truncated ? <p>도구 이력 일부만 표시됩니다.</p> : null}
                {!run ? <p>현재 실행의 도구 이력은 실행 후 확인할 수 있습니다.</p> : null}
            </div>
            {run ? (
                <Button
                    type="button"
                    disabled={!actions.canCancel || state.operation?.kind === "cancelling"}
                    onClick={() => {
                        void controller.cancelRun();
                    }}
                    data-testid="run-cancel"
                >
                    {run.status === "cancelling" ? "취소 요청 중" : "취소 요청"}
                </Button>
            ) : null}
            {run?.terminal ? (
                <p role="status">
                    {run.terminal.message ?? statusLabels[run.terminal.status]}
                    {run.terminal.reason_code ? ` · ${run.terminal.reason_code}` : ""}
                </p>
            ) : null}
            <form onSubmit={actions.submit} className="stack-form">
                <TextAreaField
                    id="question-input"
                    label="질문 입력"
                    value={actions.prompt}
                    maxLength={32000}
                    rows={3}
                    onChange={(event) => actions.setPrompt(event.currentTarget.value)}
                    onKeyDown={actions.onPromptKeyDown}
                    data-testid="question-input"
                />
                <p className="muted-copy">Enter로 전송 · Shift+Enter로 줄 바꿈</p>
                <Button
                    type="submit"
                    variant="primary"
                    disabled={!actions.canSubmit || !runCanContinue}
                    data-testid="question-submit"
                >
                    질문 fixture 실행
                </Button>
            </form>
            <details>
                <summary>빈 대화·오류·무결과 예시</summary>
                <p>질문을 입력해 시작하세요.</p>
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
                    {fixtureAdapter.runs[1]!.terminal?.status ?? fixtureAdapter.runs[1]!.status} ·{" "}
                    {fixtureAdapter.runs[1]!.answer.truncated ? "일부 표시" : "답변 완료"}
                </p>
                <p>{fixtureAdapter.runs[2]!.terminal?.status ?? fixtureAdapter.runs[2]!.status}</p>
            </details>
        </section>
    );
}

function isTerminalWithoutAnswer(run: NonNullable<RunViewState["snapshot"]>): boolean {
    return (
        (run.status === "completed" || run.status === "failed" || run.status === "cancelled") &&
        run.answer.text.length === 0
    );
}
