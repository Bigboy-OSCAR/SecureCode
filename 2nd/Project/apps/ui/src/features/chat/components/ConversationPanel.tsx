import { Alert, Button, StatusBadge, TextAreaField } from "../../../components/index.js";
import { AnswerView } from "./AnswerView.js";
import { ToolHistory } from "./ToolHistory.js";
import { useConversationActions } from "../hooks/useConversationActions.js";
import type { RunController } from "../model/runController.js";
import type { RunViewState } from "../model/runState.js";

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
                <span role="status" aria-live="polite">
                    <StatusBadge label={currentStatus} tone={run ? "warning" : "neutral"} />
                </span>
            </div>
            {run ? (
                <p>
                    세션 {run.session_id} · 실행 {run.run_id}
                </p>
            ) : (
                <p>호스트 SDK에 질문을 보내고 상태를 이벤트 스트림으로 받습니다.</p>
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
            <ToolHistory key={run?.run_id} run={run} />
            <AnswerView run={run} />
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
                    호스트에 질문 보내기
                </Button>
            </form>
        </section>
    );
}
