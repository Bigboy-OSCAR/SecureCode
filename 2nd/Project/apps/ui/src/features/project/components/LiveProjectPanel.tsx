import { useRef, useState, type FormEvent } from "react";
import type { IdempotencyKey, Session, Workspace, WorkspaceId } from "@securecode/contracts";
import { Alert, Button, InputField, StatusBadge } from "../../../components/index.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import { createIdempotencyKey } from "../../../api/runClient.js";

export interface LiveProjectPanelProps {
    connected: boolean;
    workspaces: Workspace[];
    selectedWorkspace: Workspace | null;
    session: Session | null;
    onRegister: (displayName: string, rootPath: string, idempotencyKey: IdempotencyKey) => Promise<Workspace>;
    onStartSession: (workspace: Workspace, idempotencyKey: IdempotencyKey) => Promise<Session>;
}

export function LiveProjectPanel({
    connected,
    workspaces,
    selectedWorkspace,
    session,
    onRegister,
    onStartSession,
}: LiveProjectPanelProps): React.JSX.Element {
    const [displayName, setDisplayName] = useState("");
    const [rootPath, setRootPath] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const workspaceRequest = useRef<{ fingerprint: string; key: IdempotencyKey } | null>(null);
    const sessionRequests = useRef(new Map<WorkspaceId, IdempotencyKey>());

    const submitRegistration = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
        event.preventDefault();
        const fingerprint = `${displayName}\0${rootPath}`;
        if (workspaceRequest.current?.fingerprint !== fingerprint) {
            workspaceRequest.current = { fingerprint, key: createIdempotencyKey() };
        }
        setBusy(true);
        setError(null);
        try {
            await onRegister(displayName, rootPath, workspaceRequest.current.key);
            workspaceRequest.current = null;
        } catch (requestError) {
            setError(formatApiFailure(requestError, "프로젝트 등록 결과를 확인하지 못했습니다."));
        } finally {
            setBusy(false);
        }
    };

    const openSession = async (workspace: Workspace): Promise<void> => {
        const key = sessionRequests.current.get(workspace.workspace_id) ?? createIdempotencyKey();
        sessionRequests.current.set(workspace.workspace_id, key);
        setBusy(true);
        setError(null);
        try {
            await onStartSession(workspace, key);
            sessionRequests.current.delete(workspace.workspace_id);
        } catch (requestError) {
            setError(formatApiFailure(requestError, "세션을 시작하지 못했습니다."));
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className="feature-card" aria-labelledby="project-heading" data-testid="screen-project">
            <div className="feature-heading">
                <h2 id="project-heading">프로젝트</h2>
                <StatusBadge
                    label={selectedWorkspace?.display_name ?? (connected ? "프로젝트 선택 필요" : "연결 대기")}
                    tone="neutral"
                />
            </div>
            <form onSubmit={(event) => void submitRegistration(event)} className="stack-form">
                <InputField
                    id="project-display-name"
                    label="표시 이름"
                    value={displayName}
                    maxLength={120}
                    onChange={(event) => setDisplayName(event.currentTarget.value)}
                    data-testid="project-name"
                />
                <InputField
                    id="project-root-path"
                    label="로컬 프로젝트 경로"
                    value={rootPath}
                    maxLength={4096}
                    onChange={(event) => setRootPath(event.currentTarget.value)}
                    data-testid="project-path"
                />
                <Button
                    type="submit"
                    variant="primary"
                    disabled={!connected || busy || !displayName.trim() || !rootPath.trim()}
                    data-testid="project-register"
                >
                    프로젝트 등록
                </Button>
            </form>
            {!connected ? <p role="status">호스트에 연결한 뒤 프로젝트를 등록하세요.</p> : null}
            {error ? (
                <Alert title="프로젝트 요청을 확인하세요" variant="error">
                    {error}
                </Alert>
            ) : null}
            {workspaces.length > 0 ? (
                <ul className="compact-list" aria-label="등록된 프로젝트">
                    {workspaces.map((workspace) => (
                        <li key={workspace.workspace_id}>
                            <span>{workspace.display_name}</span>
                            <Button
                                type="button"
                                disabled={!connected || busy}
                                onClick={() => void openSession(workspace)}
                            >
                                이 프로젝트에서 세션 시작
                            </Button>
                        </li>
                    ))}
                </ul>
            ) : connected ? (
                <p role="status">등록된 프로젝트가 없습니다.</p>
            ) : null}
            {selectedWorkspace ? (
                <div className="message-card">
                    <h3>색인 준비 상태</h3>
                    <p>
                        {selectedWorkspace.index_status} · revision {selectedWorkspace.index_revision ?? "없음"}
                    </p>
                    <p>색인 API는 아직 준비되지 않았습니다. 검색 가능하거나 완료된 것으로 표시하지 않습니다.</p>
                </div>
            ) : null}
            {session ? <p role="status">세션이 호스트에 생성되었습니다. 실행 전 보호 상태를 확인합니다.</p> : null}
        </section>
    );
}
