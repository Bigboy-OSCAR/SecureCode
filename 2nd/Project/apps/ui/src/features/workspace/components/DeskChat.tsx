/** Live chat restores the last server run and preserves earlier turns while streaming a new one. */
import { useEffect, useRef, useState } from "react";
import type { RunSnapshot, Session, Workspace, SelectedPointerContextRef } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import type { HttpRunClient } from "../../../api/httpRunClient.js";
import { useRunController } from "../../chat/hooks/useRunController.js";
import { useConversationActions } from "../../chat/hooks/useConversationActions.js";
import { useChatScroll } from "../../chat/hooks/useChatScroll.js";
import { AnswerView } from "../../chat/components/AnswerView.js";
import { ToolHistory } from "../../chat/components/ToolHistory.js";
import { ApprovalCard } from "../../approvals/components/ApprovalCard.js";
import { Alert, Button, TextAreaField } from "../../../components/index.js";
import { DeskIcon } from "../../../components/DeskIcon.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import { formatSelection } from "../../shared/model/provenanceLabels.js";
import { DeskWelcome } from "./DeskWelcome.js";

const STATUS = {
    queued: "실행 대기 중",
    running: "실행 중",
    awaiting_approval: "승인 대기 중",
    cancelling: "취소 요청 중",
    completed: "완료",
    failed: "실패",
    cancelled: "취소됨",
} as const;
interface Props {
    api: ApiHttpClient;
    client: HttpRunClient;
    session: Session;
    workspace: Workspace;
    contextRef: SelectedPointerContextRef | null;
    onClearContext: () => void;
    canSend: boolean;
    onAttach: () => void;
    onRunChanged: () => Promise<void>;
    onRuntimePointer: (pointer: string | null, runId: string | null) => void;
}
export function DeskChat({
    api,
    client,
    session,
    workspace,
    contextRef,
    onClearContext,
    canSend,
    onAttach,
    onRunChanged,
    onRuntimePointer,
}: Props): React.JSX.Element {
    const { controller, state } = useRunController(client, session.session_id, workspace.workspace_id);
    const actions = useConversationActions(controller, state, contextRef ? [contextRef] : []);
    const [history, setHistory] = useState<RunSnapshot[]>([]);
    const [restoreError, setRestoreError] = useState<string | null>(null);
    const [restoring, setRestoring] = useState(true);
    const chatScroll = useChatScroll(session.session_id, restoring);
    const lastSnapshot = useRef<RunSnapshot | null>(null);
    const run = state.snapshot;
    useEffect(() => {
        let live = true;
        setRestoring(true);
        setRestoreError(null);
        setHistory([]);
        void (async () => {
            const summaries = [];
            let cursor: string | undefined;
            do {
                const page = await api.listRuns(session.session_id, cursor);
                summaries.push(...page.items);
                cursor = page.page.next_cursor ?? undefined;
            } while (cursor);
            const snapshots = await Promise.all(summaries.map((item) => api.getRun(item.run_id)));
            snapshots.sort((a, b) => a.created_at.localeCompare(b.created_at));
            if (!live) return;
            setHistory(snapshots);
            const latest = snapshots.at(-1);
            if (latest) controller.restore(latest);
        })()
            .catch((failure: unknown) => {
                if (live) setRestoreError(formatApiFailure(failure, "대화 복구에 실패했습니다."));
            })
            .finally(() => {
                if (live) setRestoring(false);
            });
        return () => {
            live = false;
        };
    }, [api, controller, session.session_id]);
    useEffect(() => {
        if (!run) return;
        const previous = lastSnapshot.current;
        if (previous && previous.run_id !== run.run_id)
            setHistory((rows) => [...rows.filter((row) => row.run_id !== previous.run_id), previous]);
        lastSnapshot.current = run;
    }, [run]);
    useEffect(() => {
        if (run) void onRunChanged();
    }, [run?.run_id, run?.status, onRunChanged]);
    useEffect(() => {
        onRuntimePointer(
            state.pointerCreated?.kind === "runtime" ? state.pointerCreated.pointer : null,
            run?.run_id ?? null,
        );
    }, [onRuntimePointer, run?.run_id, state.pointerCreated]);
    const preceding = history.filter((item) => item.run_id !== run?.run_id);
    return (
        <section className="desk-chat" id="screen-chat" data-testid="screen-chat" aria-label="대화 · 실행 이력">
            <div
                className="desk-messages"
                aria-busy={restoring}
                ref={chatScroll.messagesRef}
                onScroll={chatScroll.onScroll}
            >
                {restoring ? <p role="status">대화를 불러오는 중…</p> : null}
                {restoreError ? (
                    <Alert title="대화를 확인하세요" variant="error">
                        {restoreError}
                    </Alert>
                ) : null}
                {!run && !restoring ? (
                    <DeskWelcome
                        name={workspace.display_name}
                        path={workspace.display_path}
                        onSuggestion={actions.setPrompt}
                    />
                ) : null}
                {preceding.map((item) => (
                    <div key={item.run_id}>
                        <div className="desk-user-message">{item.prompt_preview}</div>
                        <AnswerView run={item} />
                    </div>
                ))}
                {run ? (
                    <>
                        <p className="desk-date">{new Date(run.created_at).toLocaleDateString("ko-KR")}</p>
                        <div className="desk-user-message">{run.prompt_preview}</div>
                        <div className="desk-response-title">
                            <span>
                                <DeskIcon name="imgIconTerminal1" />
                            </span>
                            <strong>LocalDesk</strong>
                            <small>로컬</small>
                        </div>
                        <AnswerView run={run} />
                        <ToolHistory tools={run.tool_calls} truncated={run.tool_calls_truncated === true} />
                        <p className="desk-run-status" role="status">
                            {STATUS[run.status]}
                            {run.terminal?.reason_code ? ` · ${run.terminal.reason_code}` : ""}
                        </p>
                    </>
                ) : null}
                {state.connection === "disconnected" ? (
                    <Alert title="연결이 끊겼습니다" variant="warning">
                        입력과 결과가 유지됩니다.
                        <Button type="button" onClick={actions.reconnect} data-testid="run-reconnect">
                            최신 상태 다시 확인
                        </Button>
                    </Alert>
                ) : null}
                {state.error ? (
                    <Alert title="실행 상태를 확인하세요" variant="error">
                        {state.error}
                    </Alert>
                ) : null}
            </div>
            <div className="desk-composer-wrap">
                <ApprovalCard controller={controller} state={state} />
                <form
                    className="desk-composer"
                    onSubmit={(event) => {
                        if (!canSend || restoring || !actions.canSubmit) {
                            event.preventDefault();
                            return;
                        }
                        chatScroll.followLatest();
                        actions.submit(event);
                    }}
                >
                    <div className="desk-composer-context">
                        <DeskIcon name="imgIconFolder2" />
                        <span>{workspace.display_name}</span>
                        <span className="desk-tag">로컬 폴더</span>
                        {contextRef ? (
                            <span className="desk-context-chip">
                                선택 자료 · {formatSelection(contextRef.selection.range)}
                                <button type="button" onClick={onClearContext} aria-label="선택 자료 포함 해제">
                                    ×
                                </button>
                            </span>
                        ) : null}
                        <button
                            type="button"
                            className="desk-icon-button"
                            aria-label="자료와 컨텍스트 열기"
                            onClick={onAttach}
                        >
                            <DeskIcon name="imgIconPanel1" />
                        </button>
                    </div>
                    <TextAreaField
                        id="question-input"
                        label="질문 입력"
                        value={actions.prompt}
                        onChange={(event) => actions.setPrompt(event.currentTarget.value)}
                        onKeyDown={actions.onPromptKeyDown}
                        placeholder="프로젝트에 대해 무엇이든 물어보세요…"
                        maxLength={32000}
                        rows={2}
                        data-testid="question-input"
                    />
                    <div className="desk-composer-actions">
                        <button type="button" className="desk-icon-button" aria-label="자료 등록" onClick={onAttach}>
                            <DeskIcon name="imgIconPlus" />
                        </button>
                        <span>
                            {canSend ? "Enter로 전송 · Shift+Enter로 줄 바꿈" : "모델을 선택한 뒤 대화할 수 있습니다"}
                        </span>
                        {actions.canCancel ? (
                            <Button type="button" onClick={() => void controller.cancelRun()} data-testid="run-cancel">
                                취소 요청
                            </Button>
                        ) : null}
                        <button
                            type="submit"
                            className="desk-send"
                            aria-label="질문 보내기"
                            disabled={!canSend || restoring || !actions.canSubmit}
                            data-testid="question-submit"
                        >
                            <DeskIcon name="imgIconArrow" />
                        </button>
                    </div>
                </form>
                <p className="desk-privacy">
                    <DeskIcon name="imgEllipse4" />
                    대화와 파일은 이 기기에 저장됩니다
                </p>
            </div>
        </section>
    );
}
