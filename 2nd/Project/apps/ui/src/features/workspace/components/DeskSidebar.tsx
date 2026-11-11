/** Project and conversation navigation matching the LocalDesk prototype. */
import { useState } from "react";
import type { Session, Workspace } from "@securecode/contracts";
import { DeskIcon } from "../../../components/DeskIcon.js";
import type { DeskChat } from "../hooks/useDeskWorkspace.js";
import { ProjectContextMenu, type ProjectMenuTarget } from "./ProjectContextMenu.js";

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
    loadingChats: boolean;
}
export function DeskSidebar(props: Props): React.JSX.Element {
    const [menu, setMenu] = useState<ProjectMenuTarget | null>(null);
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
                            className={`desk-project ${props.workspace?.workspace_id === workspace.workspace_id ? "selected" : ""} ${menu?.workspace.workspace_id === workspace.workspace_id ? "menu-open" : ""}`}
                            onContextMenu={(event) => {
                                event.preventDefault();
                                const trigger =
                                    event.currentTarget.querySelector<HTMLButtonElement>(".desk-project-open");
                                if (trigger) setMenu({ workspace, x: event.clientX, y: event.clientY, trigger });
                            }}
                        >
                            <button
                                className="desk-project-open"
                                aria-label={workspace.display_name}
                                aria-expanded={props.workspace?.workspace_id === workspace.workspace_id}
                                onClick={() => props.onWorkspace(workspace)}
                                onKeyDown={(event) => {
                                    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
                                        event.preventDefault();
                                        const rect = event.currentTarget.getBoundingClientRect();
                                        setMenu({
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
                                onClick={() => props.onNewChat(workspace)}
                            >
                                <DeskIcon name="img" />
                            </button>
                        </div>
                        {props.workspace?.workspace_id === workspace.workspace_id ? (
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
                                        className={
                                            props.session?.session_id === chat.session.session_id ? "selected" : ""
                                        }
                                        onClick={() => props.onChat(chat.session)}
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
                <ProjectContextMenu target={menu} onClose={() => setMenu(null)} onRemove={props.onRemoveProject} />
            ) : null}
        </nav>
    );
}
