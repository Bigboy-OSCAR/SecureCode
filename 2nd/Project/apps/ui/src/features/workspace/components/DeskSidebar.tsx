/** Project and conversation navigation matching the LocalDesk prototype. */
import { useEffect, useState } from "react";
import type { Session, Workspace } from "@securecode/contracts";
import { DeskIcon } from "../../../components/DeskIcon.js";
import type { DeskChat } from "../hooks/useDeskWorkspace.js";
import { SidebarContextMenu, type SidebarMenuTarget } from "./SidebarContextMenu.js";

type MenuTarget = SidebarMenuTarget & ({ kind: "project"; workspace: Workspace } | { kind: "chat"; chat: DeskChat });

interface Props {
    modelCount: number | null;
    workspaces: Workspace[];
    workspace: Workspace | null;
    session: Session | null;
    chats: DeskChat[];
    onProject: () => void;
    onSearch: () => void;
    onModels: () => void;
    onIndex: () => void;
    onSettings: () => void;
    onWorkspace: (workspace: Workspace) => void;
    onChat: (session: Session) => void;
    onNewChat: (workspace: Workspace) => void;
    onRemoveProject: (workspace: Workspace) => Promise<boolean>;
    onRemoveChat: (session: Session) => Promise<boolean>;
    loadingChats: boolean;
    busy: boolean;
}
export function DeskSidebar(props: Props): React.JSX.Element {
    const [menu, setMenu] = useState<MenuTarget | null>(null);
    const [collapsedWorkspaceId, setCollapsedWorkspaceId] = useState<string | null>(null);
    useEffect(() => setCollapsedWorkspaceId(null), [props.workspace?.workspace_id]);
    const isExpanded = (workspace: Workspace): boolean =>
        props.workspace?.workspace_id === workspace.workspace_id && collapsedWorkspaceId !== workspace.workspace_id;
    return (
        <nav id="project-panel" className="desk-sidebar" aria-label="프로젝트 및 대화">
            <div className="desk-brand">
                <DeskIcon name="imgIconTerminal" />
                <strong>LocalDesk</strong>
                <span className="desk-tag">LOCAL</span>
            </div>
            <button className="desk-nav-row" onClick={props.onSearch}>
                <DeskIcon name="imgIconSearch" />
                대화 검색<kbd>⌘ K</kbd>
            </button>
            <div className="desk-section-label">
                <span>프로젝트</span>
                <button className="desk-icon-button" aria-label="프로젝트 추가" onClick={props.onProject}>
                    <DeskIcon name="imgIconPlus" />
                </button>
            </div>
            <div className="desk-projects">
                {props.workspaces.map((workspace) => (
                    <div key={workspace.workspace_id}>
                        <div
                            className={`desk-project ${props.workspace?.workspace_id === workspace.workspace_id ? "selected" : ""} ${menu?.kind === "project" && menu.workspace.workspace_id === workspace.workspace_id ? "menu-open" : ""}`}
                            onContextMenu={(event) => {
                                event.preventDefault();
                                const trigger =
                                    event.currentTarget.querySelector<HTMLButtonElement>(".desk-project-open");
                                if (trigger)
                                    setMenu({
                                        kind: "project",
                                        workspace,
                                        x: event.clientX,
                                        y: event.clientY,
                                        trigger,
                                    });
                            }}
                        >
                            <button
                                className="desk-project-open"
                                aria-label={workspace.display_name}
                                aria-expanded={isExpanded(workspace)}
                                onClick={() => {
                                    if (isExpanded(workspace)) setCollapsedWorkspaceId(workspace.workspace_id);
                                    else {
                                        setCollapsedWorkspaceId(null);
                                        props.onWorkspace(workspace);
                                    }
                                }}
                                onKeyDown={(event) => {
                                    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
                                        event.preventDefault();
                                        const rect = event.currentTarget.getBoundingClientRect();
                                        setMenu({
                                            kind: "project",
                                            workspace,
                                            x: rect.left + 12,
                                            y: rect.bottom,
                                            trigger: event.currentTarget,
                                        });
                                    }
                                }}
                            >
                                <span className="desk-project-label">
                                    <DeskIcon name="imgIconFolder" />
                                    <span>{workspace.display_name}</span>
                                </span>
                                {props.workspace?.workspace_id === workspace.workspace_id ? (
                                    <span
                                        className="desk-project-path"
                                        title={workspace.display_path ?? workspace.display_name}
                                    >
                                        {workspace.display_path ?? workspace.display_name}
                                    </span>
                                ) : null}
                            </button>
                            <button
                                className="desk-icon-button desk-project-new-chat"
                                aria-label={`${workspace.display_name} 새 대화`}
                                disabled={props.busy}
                                onClick={() => {
                                    setCollapsedWorkspaceId(null);
                                    props.onNewChat(workspace);
                                }}
                            >
                                <DeskIcon name="img" />
                            </button>
                        </div>
                        {isExpanded(workspace) ? (
                            <div className="desk-chat-list" aria-label="대화 목록">
                                {props.loadingChats ? (
                                    <p className="muted-copy" role="status">
                                        대화를 불러오는 중…
                                    </p>
                                ) : null}
                                {!props.loadingChats && props.chats.length === 0 ? (
                                    <p className="muted-copy">아직 이전 대화가 없어요.</p>
                                ) : null}
                                {props.chats.map((chat) => (
                                    <button
                                        key={chat.session.session_id}
                                        className={`${props.session?.session_id === chat.session.session_id ? "selected" : ""} ${menu?.kind === "chat" && menu.chat.session.session_id === chat.session.session_id ? "menu-open" : ""}`}
                                        data-session-id={chat.session.session_id}
                                        onClick={() => props.onChat(chat.session)}
                                        onContextMenu={(event) => {
                                            event.preventDefault();
                                            setMenu({
                                                kind: "chat",
                                                chat,
                                                x: event.clientX,
                                                y: event.clientY,
                                                trigger: event.currentTarget,
                                            });
                                        }}
                                        onKeyDown={(event) => {
                                            if (
                                                event.key === "ContextMenu" ||
                                                (event.shiftKey && event.key === "F10")
                                            ) {
                                                event.preventDefault();
                                                const rect = event.currentTarget.getBoundingClientRect();
                                                setMenu({
                                                    kind: "chat",
                                                    chat,
                                                    x: rect.left + 12,
                                                    y: rect.bottom,
                                                    trigger: event.currentTarget,
                                                });
                                            }
                                        }}
                                        title={chat.title}
                                    >
                                        {chat.title}
                                    </button>
                                ))}
                            </div>
                        ) : null}
                    </div>
                ))}
                <button className="desk-add-project" onClick={props.onProject}>
                    + 프로젝트 추가
                </button>
            </div>
            <div className="desk-sidebar-bottom">
                <button className="desk-nav-row" onClick={props.onModels}>
                    <DeskIcon name="imgIconChip" />내 모델
                    <span className="desk-tag">{props.modelCount ?? "—"}</span>
                </button>
                <p className="desk-local">
                    <DeskIcon name="imgIconShield" />이 기기에서만 실행·저장
                </p>
                <div className="desk-section-label">공통 관리</div>
                <button className="desk-add-project" onClick={props.onIndex}>
                    인덱스 생성·갱신
                </button>
                <button className="desk-nav-row desk-settings" onClick={props.onSettings}>
                    연결 설정
                </button>
            </div>
            {menu ? (
                <SidebarContextMenu
                    target={menu}
                    disabled={props.busy}
                    label={
                        menu.kind === "project"
                            ? `${menu.workspace.display_name} 프로젝트 메뉴`
                            : `${menu.chat.title} 대화 메뉴`
                    }
                    actionLabel={menu.kind === "project" ? "프로젝트 삭제" : "대화 삭제"}
                    focusSelector={
                        menu.kind === "project"
                            ? ".desk-project.selected .desk-project-open"
                            : "#project-panel .desk-chat-list .selected"
                    }
                    onClose={() => setMenu(null)}
                    onRemove={() =>
                        menu.kind === "project"
                            ? props.onRemoveProject(menu.workspace)
                            : props.onRemoveChat(menu.chat.session)
                    }
                />
            ) : null}
        </nav>
    );
}
