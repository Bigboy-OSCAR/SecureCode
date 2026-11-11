import { useEffect } from "react";
import type { PointerSelection } from "@securecode/contracts";
import { Alert, Button, InputField } from "../../../components/index.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";
import {
    countModeLabel,
    formatRequestedRange,
    formatSelection,
    isNumericSelector,
    selectorLabel,
} from "../model/pointerReadFormatting.js";
import type { UiPointer } from "../../../api/mappers/pointerMapper.js";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { useLivePointerReadWorkflow } from "../hooks/useLivePointerReadWorkflow.js";

interface LivePointerReadPanelProps {
    api: ApiHttpClient;
    pointer: UiPointer | null;
    canRead: boolean;
    onSelectionChange: (pointer: UiPointer | null, selection: PointerSelection | null) => void;
}

export function LivePointerReadPanel({
    api,
    pointer,
    canRead,
    onSelectionChange,
}: LivePointerReadPanelProps): React.JSX.Element {
    const workflow = useLivePointerReadWorkflow(api, pointer);
    const supported = pointer?.supported_selectors ?? [];
    const expired = workflow.errorCode === "EXPIRED";
    const deleted =
        workflow.errorCode === "NOT_FOUND" &&
        (workflow.errorReason === "deleted" || workflow.errorReason === "session_cleared");

    useEffect(() => {
        onSelectionChange(pointer, workflow.read?.provenance.selection ?? null);
    }, [onSelectionChange, pointer, workflow.read?.provenance.selection]);

    return (
        <section className="feature-card" aria-labelledby="pointer-read-heading" data-testid="screen-pointer-read">
            <h2 id="pointer-read-heading">Source · Runtime 부분 읽기와 검색</h2>
            {!pointer ? <p role="status">목록에서 읽을 포인터를 선택하세요.</p> : null}
            <p>전체 본문 자동 다운로드를 하지 않습니다. 부분 읽기와 검색은 API cursor로 이어집니다.</p>
            {pointer ? (
                <>
                    <p>
                        {pointer.display_name} · {pointer.kind} · revision {pointer.revision} · {pointer.media_type}
                    </p>
                    <p>미리보기는 요청할 때만 읽으며 요청당 최대 4,096 bytes입니다. 나머지는 cursor로 이어 읽습니다.</p>
                    <div className="stack-form">
                        <div className="field">
                            <label className="field-label" htmlFor="pointer-selector-kind">
                                읽기 범위
                            </label>
                            <select
                                className="text-input"
                                id="pointer-selector-kind"
                                value={workflow.selectorKind}
                                disabled={!canRead || workflow.busy !== null}
                                onChange={(event) =>
                                    workflow.setSelectorKind(event.currentTarget.value as typeof workflow.selectorKind)
                                }
                            >
                                {supported.map((selector) => (
                                    <option key={selector} value={selector}>
                                        {selectorLabel(selector)}
                                    </option>
                                ))}
                            </select>
                        </div>
                        {isNumericSelector(workflow.selectorKind) ? (
                            <>
                                <InputField
                                    id="pointer-range-start"
                                    label={
                                        workflow.selectorKind === "pdf_page"
                                            ? "시작 페이지"
                                            : workflow.selectorKind === "line"
                                              ? "시작 줄"
                                              : "시작 바이트"
                                    }
                                    type="number"
                                    min={workflow.selectorKind === "byte" ? 0 : 1}
                                    value={workflow.start}
                                    disabled={!canRead || workflow.busy !== null}
                                    onChange={(event) => workflow.setStart(event.currentTarget.value)}
                                />
                                <InputField
                                    id="pointer-range-end"
                                    label="끝 범위 (선택)"
                                    type="number"
                                    min={workflow.start}
                                    value={workflow.end}
                                    disabled={!canRead || workflow.busy !== null}
                                    onChange={(event) => workflow.setEnd(event.currentTarget.value)}
                                />
                            </>
                        ) : (
                            <InputField
                                id="pointer-selector-value"
                                label={workflow.selectorKind === "json_path" ? "JSON Pointer 경로" : "문서 구역"}
                                value={workflow.selectorValue}
                                disabled={!canRead || workflow.busy !== null}
                                onChange={(event) => workflow.setSelectorValue(event.currentTarget.value)}
                            />
                        )}
                        <Button
                            type="button"
                            disabled={!canRead || workflow.busy !== null}
                            onClick={() => void workflow.readPointer()}
                        >
                            {workflow.busy === "read" ? "부분 읽는 중…" : "범위 읽기"}
                        </Button>
                    </div>
                    {workflow.read ? (
                        <div className="message-card" data-testid="live-pointer-preview">
                            <p>
                                요청 범위:{" "}
                                {formatRequestedRange(
                                    workflow.selectorKind,
                                    workflow.start,
                                    workflow.end,
                                    workflow.selectorValue,
                                )}
                            </p>
                            <p>
                                {workflow.read.provenance.display_name ?? pointer.display_name}
                                {workflow.read.provenance.relative_path
                                    ? ` · ${workflow.read.provenance.relative_path}`
                                    : ""}{" "}
                                · revision {workflow.read.provenance.revision} · {workflow.read.token_count} tokens (
                                {countModeLabel(workflow.read.count_mode)})
                            </p>
                            {workflow.read.provenance.selection ? (
                                <p>서비스 출처: {formatSelection(workflow.read.provenance.selection.range)}</p>
                            ) : null}
                            <pre className="bounded-code">{boundedPreview(workflow.read.content, 4096)}</pre>
                            {workflow.read.truncated ? (
                                <p>응답이 상한에 도달했습니다. cursor로 계속 읽을 수 있습니다.</p>
                            ) : null}
                            {workflow.nextReadCursor ? (
                                <Button
                                    type="button"
                                    disabled={!canRead || workflow.busy !== null}
                                    onClick={() => void workflow.readNext()}
                                >
                                    다음 부분 읽기
                                </Button>
                            ) : null}
                        </div>
                    ) : null}
                    <form
                        className="stack-form"
                        onSubmit={(event) => {
                            event.preventDefault();
                            void workflow.searchPointer();
                        }}
                    >
                        <InputField
                            id="pointer-search-query"
                            label="포인터 내용 검색"
                            value={workflow.query}
                            maxLength={2000}
                            disabled={!canRead || workflow.busy !== null}
                            onChange={(event) => workflow.setQuery(event.currentTarget.value)}
                        />
                        <Button type="submit" disabled={!canRead || workflow.busy !== null}>
                            {workflow.busy === "search" ? "검색 중…" : "포인터 검색"}
                        </Button>
                    </form>
                    {workflow.searchCompleted && workflow.matches.length === 0 ? (
                        <Alert title="NO_MATCH · 검색 결과 없음" variant="info">
                            다른 검색어를 입력하세요. 전체 문서는 자동으로 내려받지 않습니다.
                        </Alert>
                    ) : null}
                    {workflow.matches.length > 0 ? (
                        <ul className="compact-list">
                            {workflow.matches.map((match, position) => (
                                <li key={`${match.byte_offset}-${position}`}>
                                    줄 {match.line} · byte {match.byte_offset}
                                    {match.selection ? ` · ${formatSelection(match.selection.range)}` : ""}
                                    <pre className="bounded-code">{boundedPreview(match.content, 512)}</pre>
                                </li>
                            ))}
                        </ul>
                    ) : null}
                    {workflow.nextSearchCursor ? (
                        <Button
                            type="button"
                            disabled={!canRead || workflow.busy !== null}
                            onClick={() => void workflow.searchNext()}
                        >
                            다음 검색 결과
                        </Button>
                    ) : null}
                </>
            ) : null}
            <PointerReadFailureNotice
                error={workflow.error}
                code={workflow.errorCode}
                reason={workflow.errorReason}
                expired={expired}
                deleted={deleted}
            />
            {!canRead ? <p role="status">호스트 연결을 복구한 뒤 다시 요청하세요.</p> : null}
        </section>
    );
}

export function PointerReadFailureNotice({
    error,
    code,
    expired,
    deleted,
}: {
    error: string | null;
    code: string | null;
    reason: string | null;
    expired: boolean;
    deleted: boolean;
}): React.JSX.Element | null {
    if (expired) {
        return (
            <Alert title="Runtime Pointer expired" variant="warning">
                실행 결과 보관 기간이 끝났습니다. 다시 실행하거나 새 Runtime Pointer를 선택하세요.
            </Alert>
        );
    }
    if (deleted) {
        return (
            <Alert title="Runtime Pointer deleted" variant="warning">
                삭제되었거나 세션 정리로 제거된 실행 결과입니다. 목록을 새로고침하세요.
            </Alert>
        );
    }
    if (code === "SOURCE_CHANGED") {
        return (
            <Alert title="원본 변경됨" variant="warning">
                이 미리보기는 폐기했습니다. Source 목록에서 등록 갱신 후 다시 읽으세요.
            </Alert>
        );
    }
    if (code === "BUDGET_EXCEEDED") {
        return (
            <Alert title="BUDGET_EXCEEDED" variant="warning">
                {error}
            </Alert>
        );
    }
    if (code === "NO_MATCH") {
        return (
            <Alert title="NO_MATCH · 검색 결과 없음" variant="info">
                다른 검색어를 입력하세요. 전체 문서는 자동으로 내려받지 않습니다.
            </Alert>
        );
    }
    return error ? (
        <Alert title="포인터 읽기·검색 실패" variant="error">
            {error}
        </Alert>
    ) : null;
}
