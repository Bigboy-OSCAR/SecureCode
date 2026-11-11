/** LocalDesk workspace composition. Feature panels retain their authenticated host workflows. */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { PointerSelection, SelectedPointerContextRef } from "@securecode/contracts";
import { ApiHttpClient } from "../api/httpClient.js";
import { HttpRunClient } from "../api/httpRunClient.js";
import { SseClient } from "../api/events/sseClient.js";
import type { UiPointer } from "../api/mappers/pointerMapper.js";
import { Button, Modal } from "../components/index.js";
import { DeskIcon } from "../components/DeskIcon.js";
import { useDeskWorkspace, type DeskChat as Chat } from "../features/workspace/hooks/useDeskWorkspace.js";
import { useDeskModels } from "../features/workspace/hooks/useDeskModels.js";
import { DeskSidebar } from "../features/workspace/components/DeskSidebar.js";
import { DeskChat } from "../features/workspace/components/DeskChat.js";
import { DeskWelcome } from "../features/workspace/components/DeskWelcome.js";
import { ProjectDialog } from "../features/workspace/components/ProjectDialog.js";
import { IndexDialog } from "../features/workspace/components/IndexDialog.js";
import { ModelDialog } from "../features/workspace/components/ModelDialog.js";
import { HistoryPanel, SearchDialog } from "../features/workspace/components/HistoryPanel.js";
import { useIndexWorkflow } from "../features/project/hooks/useIndexWorkflow.js";
import { LiveContextPanel } from "../features/context/components/LiveContextPanel.js";
import { LivePointerWorkspace } from "../features/pointers/components/LivePointerWorkspace.js";
import { LiveConnectionPanel } from "../features/settings/components/LiveConnectionPanel.js";

type Dialog = "project" | "search" | "models" | "manage" | "index" | "settings" | null;
export function LiveApp(): React.JSX.Element {
    const api = useMemo(() => new ApiHttpClient(), []);
    const runClient = useMemo(() => new HttpRunClient(api, new SseClient()), [api]);
    const desk = useDeskWorkspace(api);
    const models = useDeskModels(desk.connected);
    const [dialog, setDialog] = useState<Dialog>(null);
    const [historyOpen, setHistoryOpen] = useState(false);
    const [historyChat, setHistoryChat] = useState<Chat | null>(null);
    const [contextOpen, setContextOpen] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [runtimePointerRuns, setRuntimePointerRuns] = useState<Readonly<Record<string, string>>>({});
    const [pointerContextRef, setPointerContextRef] = useState<SelectedPointerContextRef | null>(null);
    const index = useIndexWorkflow(api, desk.workspace?.workspace_id ?? null);
    const refreshIndex = useCallback((): void => {
        void index.refresh();
    }, [index.refresh]);
    const reportRuntimePointer = useCallback((pointer: string | null, runId: string | null): void => {
        if (pointer && runId)
            setRuntimePointerRuns((current) =>
                current[pointer] === runId ? current : { ...current, [pointer]: runId },
            );
    }, []);
    const reportReadSelection = useCallback((pointer: UiPointer | null, selection: PointerSelection | null): void => {
        setPointerContextRef(pointer && selection ? { kind: pointer.kind, pointer: pointer.pointer, selection } : null);
    }, []);
    useEffect(() => {
        const keydown = (event: KeyboardEvent): void => {
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                setDialog("search");
            }
        };
        window.addEventListener("keydown", keydown);
        return () => window.removeEventListener("keydown", keydown);
    }, []);
    const activeModel = models.models?.items.find((item) => item.model_id === models.models?.active_model_id);
    const configuredModel = desk.settings?.provider.configured ? desk.settings.provider.model_id : null;
    const modelName = activeModel?.display_name ?? configuredModel ?? "모델 선택 필요";
    const modelLoading = !!models.loading || models.models?.status === "loading";
    const modelReady =
        !modelLoading &&
        models.models?.status !== "error" &&
        (!!activeModel || (!models.models?.items.length && !!configuredModel));
    const chat = desk.chats.find((item) => item.session.session_id === desk.session?.session_id);
    const openContext = (): void => {
        setContextOpen(true);
        setHistoryOpen(false);
    };
    return (
        <>
            <a className="skip-link" href="#main-content">
                본문으로 건너뛰기
            </a>
            <div className={`desk-shell ${sidebarOpen ? "sidebar-open" : ""}`}>
                <div className="desk-titlebar">
                    <div className="desk-traffic">
                        <DeskIcon name="imgEllipse" />
                        <DeskIcon name="imgEllipse1" />
                        <DeskIcon name="imgEllipse2" />
                    </div>
                    <span>LocalDesk / 개인 로컬 워크스페이스</span>
                    <button
                        className="desk-icon-button"
                        aria-label="프로젝트 패널"
                        onClick={() => setSidebarOpen((value) => !value)}
                    >
                        <DeskIcon name="imgIconPanel" />
                    </button>
                </div>
                <div className="desk-body">
                    <DeskSidebar
                        modelCount={models.models?.items.length ?? null}
                        workspaces={desk.workspaces}
                        workspace={desk.workspace}
                        session={desk.session}
                        chats={desk.chats}
                        onProject={() => setDialog("project")}
                        onSearch={() => setDialog("search")}
                        onModels={() => {
                            setDialog("manage");
                            void models.refresh();
                        }}
                        onIndex={() => setDialog("index")}
                        onSettings={() => setDialog("settings")}
                        onWorkspace={(workspace) => {
                            void desk.selectWorkspace(workspace);
                            setSidebarOpen(false);
                        }}
                        onChat={(session) => {
                            desk.setSession(session);
                            setSidebarOpen(false);
                        }}
                        onNewChat={(workspace) => void desk.newChat(workspace)}
                    />
                    <main className="desk-main" id="main-content" tabIndex={-1}>
                        <header className="desk-chat-header">
                            <div className="desk-chat-title">
                                <small>{desk.workspace?.display_name ?? "LocalDesk"}</small>
                                <strong>{chat?.title ?? "새 대화"}</strong>
                            </div>
                            <button className="desk-header-button" onClick={openContext}>
                                자료 · 컨텍스트
                            </button>
                            <button
                                className="desk-header-button"
                                onClick={() => {
                                    setHistoryOpen((value) => !value);
                                    setContextOpen(false);
                                }}
                            >
                                이전 대화
                            </button>
                            <button
                                className="desk-model-picker"
                                onClick={() => {
                                    setDialog("models");
                                    void models.refresh();
                                }}
                            >
                                <DeskIcon name="imgEllipse3" />
                                <span>{modelName}</span>
                                <DeskIcon name="imgIconDown1" />
                                <small>{modelLoading ? "불러오는 중" : modelReady ? "실행 중" : "선택"}</small>
                            </button>
                        </header>
                        {desk.error ? (
                            <p className="desk-inline-error" role="alert">
                                {desk.error}
                            </p>
                        ) : null}
                        {!desk.connected ? (
                            <div className="desk-connect-prompt">
                                <p>로컬 서비스에 연결하면 프로젝트와 대화를 불러옵니다.</p>
                                <Button variant="primary" onClick={() => setDialog("settings")}>
                                    연결 설정
                                </Button>
                            </div>
                        ) : null}
                        {desk.session && desk.workspace ? (
                            <DeskChat
                                key={desk.session.session_id}
                                api={api}
                                client={runClient}
                                session={desk.session}
                                workspace={desk.workspace}
                                contextRef={pointerContextRef}
                                onClearContext={() => setPointerContextRef(null)}
                                canSend={desk.connected && modelReady}
                                onAttach={openContext}
                                onRunChanged={desk.refreshChats}
                                onRuntimePointer={reportRuntimePointer}
                            />
                        ) : (
                            <div className="desk-empty">
                                <DeskWelcome
                                    name={desk.workspace?.display_name ?? null}
                                    path={desk.workspace?.display_path}
                                />
                                <Button
                                    variant="primary"
                                    disabled={!desk.connected || desk.busy}
                                    onClick={() => (desk.workspace ? void desk.newChat() : setDialog("project"))}
                                >
                                    {desk.workspace ? "새 대화 시작" : "프로젝트 추가"}
                                </Button>
                            </div>
                        )}
                    </main>
                    {historyOpen ? (
                        <HistoryPanel
                            api={api}
                            chat={historyChat}
                            chats={desk.chats}
                            onSelect={setHistoryChat}
                            onClose={() => setHistoryOpen(false)}
                            onContinue={(session) => {
                                desk.setSession(session);
                                setHistoryOpen(false);
                            }}
                        />
                    ) : null}
                    <aside
                        id="context-panel"
                        className="desk-context-panel"
                        hidden={!contextOpen}
                        aria-label="자료와 컨텍스트"
                    >
                        <div className="desk-drawer-heading">
                            <h2>자료 · 컨텍스트</h2>
                            <Button variant="quiet" onClick={() => setContextOpen(false)}>
                                닫기
                            </Button>
                        </div>
                        <div className="desk-context-scroll">
                            <LiveContextPanel
                                api={api}
                                connected={desk.connected}
                                workspaceId={desk.workspace?.workspace_id ?? null}
                                sessionId={desk.session?.session_id ?? null}
                                index={index.status}
                                pointerContextRef={pointerContextRef}
                                onSourceChanged={refreshIndex}
                            />
                            <LivePointerWorkspace
                                api={api}
                                connected={desk.connected}
                                workspaceId={desk.workspace?.workspace_id ?? null}
                                sessionId={desk.session?.session_id ?? null}
                                runtimePointerRuns={runtimePointerRuns}
                                onReadSelection={reportReadSelection}
                            />
                        </div>
                    </aside>
                </div>
            </div>
            <ProjectDialog
                open={dialog === "project"}
                connected={desk.connected}
                onClose={() => setDialog(null)}
                onRegister={desk.register}
            />
            <IndexDialog
                open={dialog === "index"}
                onClose={() => setDialog(null)}
                api={api}
                workspaces={desk.workspaces}
                selectedId={desk.workspace?.workspace_id}
                onUpdated={refreshIndex}
            />
            <ModelDialog
                open={dialog === "models" || dialog === "manage"}
                manage={dialog === "manage"}
                onClose={() => setDialog(null)}
                onManage={() => setDialog("manage")}
                state={models}
            />
            <SearchDialog
                open={dialog === "search"}
                chats={desk.chats}
                onClose={() => setDialog(null)}
                onSelect={(selected) => {
                    setHistoryChat(selected);
                    setHistoryOpen(true);
                    setContextOpen(false);
                    setDialog(null);
                }}
            />
            <Modal open={dialog === "settings"} title="연결 설정" onRequestClose={() => setDialog(null)}>
                <LiveConnectionPanel
                    api={api}
                    connected={desk.connected}
                    health={desk.health}
                    settings={desk.settings}
                    onAuthenticated={() => void desk.refresh()}
                    onStatus={desk.onStatus}
                />
            </Modal>
        </>
    );
}
