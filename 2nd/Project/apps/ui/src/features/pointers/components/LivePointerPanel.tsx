import { useState, type FormEvent } from "react";
import type { SessionId, WorkspaceId } from "@securecode/contracts";
import { Alert, Button, InputField, Modal, StatusBadge } from "../../../components/index.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";
import { isSourcePathValid } from "../model/pointerForm.js";
import type { UiPointer } from "../../../api/mappers/pointerMapper.js";
import type { useLivePointerCatalog } from "../hooks/useLivePointerCatalog.js";

interface LivePointerPanelProps {
    workspaceId: WorkspaceId | null;
    sessionId: SessionId | null;
    runtimePointerRun: { pointer: string; runId: string } | null;
    canMutate: boolean;
    catalog: ReturnType<typeof useLivePointerCatalog>;
}

export function LivePointerPanel({
    workspaceId,
    sessionId,
    runtimePointerRun,
    canMutate,
    catalog,
}: LivePointerPanelProps): React.JSX.Element {
    const [externalPath, setExternalPath] = useState("");
    const [pendingDelete, setPendingDelete] = useState<UiPointer | null>(null);
    const selectedSource = catalog.selectedPointer?.kind === "source" ? catalog.selectedPointer : null;

    const submitRegistration = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
        event.preventDefault();
        if (isSourcePathValid(externalPath)) {
            await catalog.registerExternalFile(externalPath.trim());
        }
    };

    const deleteSelected = async (): Promise<void> => {
        if (pendingDelete) {
            await catalog.removePointer(pendingDelete);
            setPendingDelete(null);
        }
    };

    return (
        <section className="feature-card" aria-labelledby="pointers-heading" data-testid="screen-pointers">
            <div className="feature-heading">
                <h2 id="pointers-heading">Source · Runtime Pointer</h2>
                <StatusBadge label={sessionId ? "프로젝트·세션 범위" : "세션 필요"} tone="neutral" />
            </div>
            <form onSubmit={(event) => void submitRegistration(event)} className="stack-form">
                <InputField
                    id="source-external-path"
                    label="등록할 외부 파일의 호스트 경로"
                    value={externalPath}
                    maxLength={4096}
                    disabled={!canMutate || catalog.busy !== null}
                    onChange={(event) => setExternalPath(event.currentTarget.value)}
                    data-testid="live-source-path"
                />
                <Button
                    type="submit"
                    variant="primary"
                    disabled={!canMutate || !workspaceId || catalog.busy !== null || !isSourcePathValid(externalPath)}
                    data-testid="live-source-register"
                >
                    {catalog.busy === "register" ? "등록 중…" : "지정한 파일 등록"}
                </Button>
            </form>
            <p className="muted-copy">
                브라우저는 디스크 파일을 읽지 않습니다. 입력한 경로만 host API에 보내며 Source 등록 해제는 원본을 지우지
                않습니다.
            </p>
            {catalog.error ? (
                <Alert title="포인터 요청을 확인하세요" variant="error">
                    {catalog.error}
                </Alert>
            ) : null}
            {catalog.notice ? <p role="status">{catalog.notice}</p> : null}
            {!canMutate ? <p role="status">호스트 연결이 복구되면 자료를 조회하거나 변경할 수 있습니다.</p> : null}
            <div className="pointer-entry">
                <h3>등록한 Source</h3>
                {selectedSource ? (
                    <Button
                        type="button"
                        disabled={!canMutate || catalog.busy !== null}
                        onClick={() => void catalog.refreshSource(selectedSource)}
                    >
                        선택한 Source 등록 갱신
                    </Button>
                ) : null}
                {catalog.sourcePage.items.length === 0 ? <p>등록한 Source Pointer가 없습니다.</p> : null}
                <ul className="compact-list">
                    {catalog.sourcePage.items.map((pointer) => (
                        <li key={pointer.pointer}>
                            <label>
                                <input
                                    type="radio"
                                    name="selected-pointer"
                                    checked={catalog.selectedPointer?.pointer === pointer.pointer}
                                    onChange={() => catalog.selectPointer(pointer)}
                                />
                                {pointer.display_name} · {pointer.media_type} · {pointer.byte_size.toLocaleString()}{" "}
                                bytes · revision {pointer.revision}
                            </label>
                            <p>{boundedPreview(pointer.preview, 120)}</p>
                            <Button type="button" disabled={!canMutate} onClick={() => setPendingDelete(pointer)}>
                                등록 해제
                            </Button>
                        </li>
                    ))}
                </ul>
                {catalog.sourcePage.hasMore ? (
                    <Button
                        type="button"
                        disabled={!canMutate || catalog.busy !== null}
                        onClick={() => void catalog.loadMore("source")}
                    >
                        다음 Source 목록
                    </Button>
                ) : null}
            </div>
            <div className="pointer-entry">
                <h3>현재 세션의 Runtime Pointer</h3>
                {!sessionId ? <p>프로젝트 세션을 시작하면 해당 세션의 실행 결과만 조회합니다.</p> : null}
                {sessionId ? (
                    <Button
                        type="button"
                        disabled={!canMutate || catalog.busy !== null}
                        onClick={() => void catalog.refreshRuntime()}
                    >
                        Runtime 목록 새로고침
                    </Button>
                ) : null}
                {sessionId && catalog.runtimePage.items.length === 0 ? <p>저장된 실행 결과가 없습니다.</p> : null}
                <ul className="compact-list">
                    {catalog.runtimePage.items.map((pointer) => {
                        const expired = pointer.expires_at ? Date.parse(pointer.expires_at) <= Date.now() : false;
                        const runId = runtimePointerRun?.pointer === pointer.pointer ? runtimePointerRun.runId : null;
                        return (
                            <li key={pointer.pointer}>
                                <label>
                                    <input
                                        type="radio"
                                        name="selected-pointer"
                                        checked={catalog.selectedPointer?.pointer === pointer.pointer}
                                        onChange={() => catalog.selectPointer(pointer)}
                                    />
                                    {pointer.display_name} · {pointer.byte_size.toLocaleString()} bytes
                                </label>
                                <p>
                                    도구: {pointer.provenance.origin} · 생성:{" "}
                                    {formatTime(pointer.provenance.created_at)}
                                </p>
                                <p>
                                    세션: {pointer.session_id} · 실행: {runId ?? "목록 API에서 실행 ID 미제공"}
                                </p>
                                <p>
                                    만료: {pointer.expires_at ? formatTime(pointer.expires_at) : "만료 시각 미제공"}
                                    {expired ? " · 만료됨" : ""}
                                </p>
                                <Button type="button" disabled={!canMutate} onClick={() => setPendingDelete(pointer)}>
                                    저장 결과 삭제
                                </Button>
                            </li>
                        );
                    })}
                </ul>
                {catalog.runtimePage.hasMore ? (
                    <Button
                        type="button"
                        disabled={!canMutate || catalog.busy !== null || !sessionId}
                        onClick={() => void catalog.loadMore("runtime")}
                    >
                        다음 Runtime 목록
                    </Button>
                ) : null}
            </div>
            <Modal
                open={pendingDelete !== null}
                title={pendingDelete?.kind === "source" ? "Source 등록을 해제할까요?" : "Runtime Pointer를 삭제할까요?"}
                onRequestClose={() => setPendingDelete(null)}
            >
                <p>
                    {pendingDelete?.kind === "source"
                        ? "등록과 파생 캐시만 정리합니다. 원본 파일은 삭제하지 않습니다."
                        : "이 세션의 저장 결과만 삭제합니다. 실행된 도구나 변경 사항은 되돌리지 않습니다."}
                </p>
                <div className="action-row">
                    <Button
                        type="button"
                        variant="primary"
                        disabled={!canMutate || catalog.busy !== null}
                        onClick={() => void deleteSelected()}
                    >
                        삭제 확인
                    </Button>
                    <Button type="button" onClick={() => setPendingDelete(null)}>
                        돌아가기
                    </Button>
                </div>
            </Modal>
        </section>
    );
}

function formatTime(value: string): string {
    const timestamp = Date.parse(value);
    return Number.isNaN(timestamp) ? value : new Date(timestamp).toLocaleString();
}
