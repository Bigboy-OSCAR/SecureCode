import { useEffect, useState } from "react";
import type { RunSnapshot } from "@securecode/contracts";
import { Alert } from "../../../components/index.js";
import { outputLabel, phaseLabel, toolLabel } from "../model/toolLabels.js";

const STATUS = {
    queued: "실행 대기 중",
    running: "실행 중",
    awaiting_approval: "승인 대기 중",
    cancelling: "취소 요청 중",
    completed: "완료",
    failed: "실패",
    cancelled: "취소됨",
} as const;

interface ToolHistoryProps {
    run: RunSnapshot | null;
    current?: boolean;
}

/** Activity belongs to one answer. Expansion changes presentation only, never the run. */
export function ToolHistory({ run, current = true }: ToolHistoryProps): React.JSX.Element | null {
    const active = !!run && ["queued", "running", "awaiting_approval", "cancelling"].includes(run.status);
    const [expanded, setExpanded] = useState(active);
    useEffect(() => setExpanded(active), [run?.run_id, active]);
    if (!run) return null;
    const tools = run.tool_calls;
    const truncated = run.tool_calls_truncated === true;
    const interruption =
        run.status === "failed" && run.terminal?.reason_code === "SOURCE_CHANGED" && run.terminal.message ? (
            <Alert title="인덱스 갱신이 필요합니다" variant="warning">
                {run.terminal.message}
            </Alert>
        ) : null;
    const status = (
        <span
            className={current ? "desk-run-status tool-activity-status" : "tool-activity-status"}
            role={current ? "status" : undefined}
        >
            {STATUS[run.status]}
            {run.terminal?.reason_code ? ` · ${run.terminal.reason_code}` : ""}
        </span>
    );
    if (!tools.length && !truncated)
        return (
            <>
                <div className="tool-activity-empty" data-active={active} data-testid="tool-history-empty">
                    <span>이 답변의 작업</span>
                    {status}
                    <span>{active ? "답변 작성 중" : "도구 사용 없음"}</span>
                </div>
                {interruption}
            </>
        );
    return (
        <>
            <details
                className="tool-activity"
                data-testid="tool-history"
                data-active={active}
                open={expanded}
                onToggle={(event) => setExpanded(event.currentTarget.open)}
            >
                <summary>
                    <svg
                        className="tool-activity-chevron"
                        width="14"
                        height="14"
                        viewBox="0 0 16 16"
                        fill="none"
                        aria-hidden="true"
                    >
                        <path
                            d="m6 3 5 5-5 5"
                            stroke="currentColor"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        />
                    </svg>
                    <span className="tool-activity-title">이 답변의 작업</span>
                    {status}
                    <span className="tool-activity-count">
                        {truncated ? "표시된 " : ""}도구 {tools.length}회
                    </span>
                </summary>
                <div className="tool-activity-body">
                    <p className="tool-activity-scope">위 질문에 답하는 동안 요청·실행한 작업입니다.</p>
                    <ol className="tool-activity-list">
                        {tools.map((tool) => (
                            <li
                                className="tool-row"
                                key={tool.tool_call_id}
                                data-testid="tool-row"
                                data-phase={tool.phase}
                            >
                                <div className="tool-step-heading">
                                    <strong>
                                        {toolLabel(tool.tool_name)} · {phaseLabel(tool.phase)}
                                    </strong>
                                    {tool.output_bytes !== undefined || tool.output_pointer ? (
                                        <span>{outputLabel(tool)}</span>
                                    ) : null}
                                </div>
                                <details className="tool-step-details">
                                    <summary>상세 기록</summary>
                                    <p>{tool.summary}</p>
                                    {tool.output_pointer ? (
                                        <p>자료 · 컨텍스트의 실행 결과에서 저장된 내용을 확인할 수 있어요.</p>
                                    ) : null}
                                </details>
                            </li>
                        ))}
                    </ol>
                    {truncated ? (
                        <p className="tool-activity-scope">이 답변의 작업 기록 중 일부만 표시됩니다.</p>
                    ) : null}
                </div>
            </details>
            {interruption}
        </>
    );
}
