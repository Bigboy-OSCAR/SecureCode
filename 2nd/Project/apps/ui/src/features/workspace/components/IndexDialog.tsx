/** Batch index jobs remain live when the progress dialog is closed. Percentages use server file counts. */
import { useEffect, useState } from "react";
import type { IndexStatusResponse, Workspace } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { createIdempotencyKey } from "../../../api/runClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import { Button, Modal } from "../../../components/index.js";
import { DeskIcon } from "../../../components/DeskIcon.js";
interface Props {
    open: boolean;
    onClose: () => void;
    api: ApiHttpClient;
    workspaces: Workspace[];
    selectedId?: string;
    onUpdated: () => void;
}
export function IndexDialog({ open, onClose, api, workspaces, selectedId, onUpdated }: Props): React.JSX.Element {
    const [selected, setSelected] = useState<string[]>([]);
    const [jobs, setJobs] = useState<Record<string, IndexStatusResponse>>({});
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        if (selectedId) setSelected([selectedId]);
        setError(null);
    }, [selectedId]);
    useEffect(() => {
        const pending = Object.entries(jobs).filter(
            ([, job]) => job.index_status === "queued" || job.index_status === "indexing",
        );
        if (!pending.length) return;
        const timer = setTimeout(() => {
            void Promise.all(pending.map(async ([id]) => [id, await api.getIndexStatus(id)] as const))
                .then((items) => {
                    setJobs((current) => ({ ...current, ...Object.fromEntries(items) }));
                    onUpdated();
                })
                .catch((failure: unknown) =>
                    setError(formatApiFailure(failure, "인덱스 진행 상태를 확인하지 못했습니다.")),
                );
        }, 1000);
        return () => clearTimeout(timer);
    }, [api, jobs, onUpdated]);
    const start = async (): Promise<void> => {
        setBusy(true);
        setError(null);
        setJobs({});
        try {
            for (const id of selected) {
                const result = await api.startIndex(id, { idempotency_key: createIdempotencyKey() });
                setJobs((current) => ({ ...current, [id]: result }));
            }
            onUpdated();
        } catch (failure) {
            setError(formatApiFailure(failure, "인덱스 생성을 시작하지 못했습니다."));
        } finally {
            setBusy(false);
        }
    };
    const running = Object.values(jobs).some((job) => ["queued", "indexing"].includes(job.index_status));
    return (
        <Modal
            open={open}
            title={Object.keys(jobs).length ? "인덱스 생성·갱신 진행" : "프로젝트 인덱스 생성·갱신"}
            onRequestClose={onClose}
        >
            <div className="desk-dialog-stack">
                <p className="muted-copy">
                    원하는 프로젝트를 선택하고 한 번에 인덱스를 생성하거나 갱신할 수 있어요. 저장되지 않은 변경 사항은
                    포함되지 않습니다.
                </p>
                <div className="desk-index-list">
                    <div className="desk-section-label">
                        프로젝트 선택 <span>{selected.length}개 선택됨</span>
                    </div>
                    <label className="desk-index-row">
                        <input
                            type="checkbox"
                            checked={workspaces.length > 0 && selected.length === workspaces.length}
                            disabled={busy || running}
                            onChange={(e) =>
                                setSelected(e.currentTarget.checked ? workspaces.map((w) => w.workspace_id) : [])
                            }
                        />
                        전체 선택 <small>{workspaces.length}개 프로젝트</small>
                    </label>
                    {workspaces.map((workspace) => (
                        <label className="desk-index-row" key={workspace.workspace_id}>
                            <input
                                type="checkbox"
                                checked={selected.includes(workspace.workspace_id)}
                                disabled={busy || running}
                                onChange={(event) => {
                                    const checked = event.currentTarget.checked;
                                    setSelected((ids) =>
                                        checked
                                            ? [...ids, workspace.workspace_id]
                                            : ids.filter((id) => id !== workspace.workspace_id),
                                    );
                                }}
                            />
                            <DeskIcon name="imgIconFolder" />
                            <strong>{workspace.display_name}</strong>
                            <small title={workspace.display_path ?? workspace.display_name}>
                                {workspace.display_path ?? workspace.display_name}
                            </small>
                        </label>
                    ))}
                </div>
                {Object.entries(jobs).map(([id, job]) => (
                    <div className="desk-job" key={id} role="status">
                        <strong>{workspaces.find((w) => w.workspace_id === id)?.display_name}</strong>
                        <span>
                            {job.index_status === "ready"
                                ? "완료"
                                : job.index_status === "partial"
                                  ? "부분 완료"
                                  : job.index_status === "failed"
                                    ? "실패"
                                    : "진행 중"}
                        </span>
                        <p>
                            발견 {job.counts.discovered} · 색인 {job.counts.indexed} · 제외 {job.counts.skipped} · 실패{" "}
                            {job.counts.failed}
                        </p>
                        <progress
                            max={Math.max(1, job.counts.discovered)}
                            value={job.counts.indexed + job.counts.skipped + job.counts.failed}
                        />
                        <p>revision {job.index_revision ?? "대기"}</p>
                        {job.diagnostics.map((item) => (
                            <p key={`${item.relative_path}-${item.reason_code}`}>
                                {item.relative_path}
                                {item.line ? `:${item.line}` : ""} · {item.reason_code}
                            </p>
                        ))}
                        {job.diagnostics_truncated ? <p>추가 진단은 응답 상한으로 생략되었습니다.</p> : null}
                    </div>
                ))}
                {error ? <p role="alert">{error}</p> : null}
                <p className="muted-copy">
                    모든 작업은 로컬에서 처리됩니다. 완료 후 새 인덱스로 교체하며, 실패하면 기존 인덱스를 유지합니다.
                </p>
                <div className="desk-modal-actions desk-index-actions">
                    <Button
                        type="button"
                        variant="secondary"
                        disabled={busy || running || !selected.length}
                        onClick={() => void start()}
                        data-testid="index-start"
                    >
                        {busy ? "요청 중…" : `${selected.length}개 생성·갱신`}
                    </Button>
                    <Button type="button" variant="primary" onClick={onClose}>
                        {running ? "진행 화면 닫기" : "닫기"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}
