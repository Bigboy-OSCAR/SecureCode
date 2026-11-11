import { useCallback, useEffect, useMemo, useState } from "react";
import type {
    HealthResponse,
    IdempotencyKey,
    Session,
    SettingsResponse,
    PointerSelection,
    SelectedPointerContextRef,
    Workspace,
    WorkspaceId,
} from "@securecode/contracts";
import { StatusBadge } from "../components/index.js";
import { ApiHttpClient } from "../api/httpClient.js";
import { HttpRunClient } from "../api/httpRunClient.js";
import { SseClient } from "../api/events/sseClient.js";
import { ApiClientError, formatApiFailure } from "../api/apiErrors.js";
import { ApprovalCard } from "../features/approvals/components/ApprovalCard.js";
import { ConversationPanel } from "../features/chat/components/ConversationPanel.js";
import { useRunController } from "../features/chat/hooks/useRunController.js";
import { LiveProjectPanel } from "../features/project/components/LiveProjectPanel.js";
import { useIndexWorkflow } from "../features/project/hooks/useIndexWorkflow.js";
import { LiveContextPanel } from "../features/context/components/LiveContextPanel.js";
import { LivePointerWorkspace } from "../features/pointers/components/LivePointerWorkspace.js";
import type { UiPointer } from "../api/mappers/pointerMapper.js";
import { LiveConnectionPanel } from "../features/settings/components/LiveConnectionPanel.js";

export function LiveApp(): React.JSX.Element {
    const api = useMemo(() => new ApiHttpClient(), []);
    const runClient = useMemo(() => new HttpRunClient(api, new SseClient()), [api]);
    const [connected, setConnected] = useState(false);
    const [health, setHealth] = useState<HealthResponse | null>(null);
    const [settings, setSettings] = useState<SettingsResponse | null>(null);
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);
    const [session, setSession] = useState<Session | null>(null);
    const [workspaceError, setWorkspaceError] = useState<string | null>(null);
    // Pointer URI -> run ID seen in this page's run events; a fallback for rows stored before run_id existed.
    const [runtimePointerRuns, setRuntimePointerRuns] = useState<Readonly<Record<string, string>>>({});
    const [pointerContextRef, setPointerContextRef] = useState<SelectedPointerContextRef | null>(null);
    const indexWorkflow = useIndexWorkflow(api, selectedWorkspace?.workspace_id ?? null);
    const refreshIndexStatus = indexWorkflow.refresh;
    const refreshIndex = useCallback((): void => void refreshIndexStatus(), [refreshIndexStatus]);
    const reportRuntimePointer = useCallback(
        (pointer: string | null, runId: string | null) => {
            if (pointer && runId) {
                setRuntimePointerRuns((current) =>
                    current[pointer] === runId ? current : { ...current, [pointer]: runId },
                );
            }
        },
        [setRuntimePointerRuns],
    );
    const reportReadSelection = useCallback((pointer: UiPointer | null, selection: PointerSelection | null): void => {
        setPointerContextRef(pointer && selection ? { kind: pointer.kind, pointer: pointer.pointer, selection } : null);
    }, []);

    const onAuthenticated = (): void => {
        setConnected(true);
        setWorkspaceError(null);
        void fetchAllWorkspaces(api)
            .then(setWorkspaces)
            .catch((error: unknown) =>
                setWorkspaceError(formatApiFailure(error, "등록된 프로젝트 목록을 불러오지 못했습니다.")),
            );
    };
    const onStatus = (nextHealth: HealthResponse, nextSettings: SettingsResponse): void => {
        setHealth(nextHealth);
        setSettings(nextSettings);
    };

    useEffect(() => {
        let mounted = true;
        void api
            .getSettings()
            .then(async (restoredSettings) => {
                const [restoredHealth, restoredWorkspaces] = await Promise.all([
                    api.getHealth(),
                    fetchAllWorkspaces(api),
                ]);
                if (mounted) {
                    setConnected(true);
                    setHealth(restoredHealth);
                    setSettings(restoredSettings);
                    setWorkspaces(restoredWorkspaces);
                }
            })
            .catch((error: unknown) => {
                if (mounted && !(error instanceof ApiClientError && error.kind === "unauthorized")) {
                    setWorkspaceError(formatApiFailure(error, "로컬 호스트 상태를 확인하지 못했습니다."));
                }
            });
        return () => {
            mounted = false;
        };
    }, [api]);

    const registerWorkspace = async (
        displayName: string,
        rootPath: string,
        idempotencyKey: IdempotencyKey,
    ): Promise<Workspace> => {
        const workspace = await api.createWorkspace({
            display_name: displayName,
            root_path: rootPath,
            idempotency_key: idempotencyKey,
        });
        setSelectedWorkspace(workspace);
        setSession(null);
        setRuntimePointerRuns({});
        setPointerContextRef(null);
        setWorkspaces((current) => upsertWorkspace(current, workspace));
        return workspace;
    };

    const startSession = async (workspace: Workspace, idempotencyKey: IdempotencyKey): Promise<Session> => {
        const created = await api.createSession({
            workspace_id: workspace.workspace_id,
            idempotency_key: idempotencyKey,
        });
        setSelectedWorkspace(workspace);
        setSession(created);
        setRuntimePointerRuns({});
        setPointerContextRef(null);
        return created;
    };

    return (
        <>
            <a className="skip-link" href="#main-content">
                본문으로 건너뛰기
            </a>
            <div className="workspace">
                <header className="topbar">
                    <div className="brand">
                        <span className="brand-mark" aria-hidden="true">
                            S
                        </span>
                        <span>SecureCode</span>
                    </div>
                    <div className="topbar-status" aria-label="서비스 상태">
                        <StatusBadge label={connected ? (health?.status ?? "연결됨") : "연결 대기"} tone="neutral" />
                    </div>
                    <section className="settings-summary" aria-labelledby="top-settings-heading">
                        <h2 id="top-settings-heading">설정</h2>
                        <p>실제 로컬 호스트 API · HttpOnly cookie 인증</p>
                    </section>
                </header>
                <div className="workspace-grid">
                    <nav className="project-sidebar" aria-label="프로젝트 및 화면">
                        <LiveProjectPanel
                            connected={connected}
                            workspaces={workspaces}
                            selectedWorkspace={selectedWorkspace}
                            session={session}
                            indexStatus={indexWorkflow.status}
                            indexError={indexWorkflow.error}
                            indexBusy={indexWorkflow.busy}
                            onStartIndex={indexWorkflow.start}
                            onRegister={registerWorkspace}
                            onStartSession={startSession}
                        />
                        {workspaceError ? <p role="alert">{workspaceError}</p> : null}
                        <div className="sidebar-links" aria-label="작업 영역">
                            <a className="sidebar-link sidebar-link-active" href="#screen-chat">
                                대화
                            </a>
                            <a className="sidebar-link" href="#screen-pointers">
                                등록 자료
                            </a>
                            <a className="sidebar-link" href="#screen-context">
                                컨텍스트 예산
                            </a>
                        </div>
                    </nav>
                    <main id="main-content" className="conversation" tabIndex={-1}>
                        <div className="conversation-heading">
                            <div>
                                <p className="eyebrow">대화 · 코드 작업</p>
                                <h2>호스트 실행</h2>
                            </div>
                            <StatusBadge label={session ? "세션 준비" : "세션 없음"} tone="neutral" />
                        </div>
                        <div className="feature-stack">
                            <LiveConnectionPanel
                                api={api}
                                connected={connected}
                                health={health}
                                settings={settings}
                                onAuthenticated={onAuthenticated}
                                onStatus={onStatus}
                            />
                            {session && selectedWorkspace ? (
                                <LiveRunPanel
                                    client={runClient}
                                    sessionId={session.session_id}
                                    workspaceId={selectedWorkspace.workspace_id}
                                    onRuntimePointer={reportRuntimePointer}
                                />
                            ) : (
                                <section
                                    id="screen-chat"
                                    className="feature-card"
                                    aria-labelledby="conversation-heading"
                                    data-testid="screen-chat"
                                >
                                    <h2 id="conversation-heading">대화 · 실행 이력</h2>
                                    <p>프로젝트를 선택하고 세션을 시작하면 실제 호스트에 질문을 보낼 수 있습니다.</p>
                                </section>
                            )}
                        </div>
                    </main>
                    <aside className="context-sidebar" aria-label="컨텍스트와 포인터">
                        <LiveContextPanel
                            api={api}
                            connected={connected}
                            workspaceId={selectedWorkspace?.workspace_id ?? null}
                            sessionId={session?.session_id ?? null}
                            index={indexWorkflow.status}
                            pointerContextRef={pointerContextRef}
                            onSourceChanged={refreshIndex}
                        />
                        <LivePointerWorkspace
                            api={api}
                            connected={connected}
                            workspaceId={selectedWorkspace?.workspace_id ?? null}
                            sessionId={session?.session_id ?? null}
                            runtimePointerRuns={runtimePointerRuns}
                            onReadSelection={reportReadSelection}
                        />
                    </aside>
                </div>
            </div>
        </>
    );
}

async function fetchAllWorkspaces(api: ApiHttpClient): Promise<Workspace[]> {
    const allWorkspaces: Workspace[] = [];
    let cursor: string | undefined;
    do {
        const page = await api.listWorkspaces(cursor);
        allWorkspaces.push(...page.items);
        cursor = page.page.next_cursor ?? undefined;
    } while (cursor);
    return allWorkspaces;
}

interface LiveRunPanelProps {
    client: HttpRunClient;
    sessionId: Session["session_id"];
    workspaceId: WorkspaceId;
    onRuntimePointer: (pointer: string | null, runId: string | null) => void;
}

function LiveRunPanel({ client, sessionId, workspaceId, onRuntimePointer }: LiveRunPanelProps): React.JSX.Element {
    const { controller, state } = useRunController(client, sessionId, workspaceId);
    useEffect(() => {
        const pointer = state.pointerCreated?.kind === "runtime" ? state.pointerCreated.pointer : null;
        onRuntimePointer(pointer, state.snapshot?.run_id ?? null);
    }, [onRuntimePointer, state.pointerCreated?.kind, state.pointerCreated?.pointer, state.snapshot?.run_id]);
    return (
        <>
            <ConversationPanel controller={controller} state={state} />
            <ApprovalCard controller={controller} state={state} />
        </>
    );
}

function upsertWorkspace(workspaces: Workspace[], workspace: Workspace): Workspace[] {
    const existing = workspaces.findIndex((item) => item.workspace_id === workspace.workspace_id);
    return existing < 0
        ? [...workspaces, workspace]
        : workspaces.map((item, index) => (index === existing ? workspace : item));
}
