/** Selects the live application or explicitly requested contract-fixture screens. */
import { LiveApp } from "./LiveApp.js";
import { ApprovalCard } from "../features/approvals/components/ApprovalCard.js";
import { ConversationPanel } from "../features/chat/components/ConversationPanel.js";
import { ContextPanel } from "../features/context/components/ContextPanel.js";
import { PdfParsePanel } from "../features/pointers/components/PdfParsePanel.js";
import { PointerPanel } from "../features/pointers/components/PointerPanel.js";
import { PointerReadPanel } from "../features/pointers/components/PointerReadPanel.js";
import { ProjectPanel } from "../features/project/components/ProjectPanel.js";
import { ConnectionPanel } from "../features/settings/components/ConnectionPanel.js";
import { SettingsPanel } from "../features/settings/components/SettingsPanel.js";
import { StatusBadge } from "../components/index.js";
import { fixtureRunClient } from "../api/fixtureRunClient.js";
import { fixtureAdapter } from "../api/fixtureAdapter.js";
import { useRunController } from "../features/chat/hooks/useRunController.js";

const fixtureNow = (): number => Date.parse("2026-11-04T09:01:00Z");

export interface AppProps {
    mode?: "fixture" | "live";
}

export function App({ mode = "fixture" }: AppProps): React.JSX.Element {
    if (mode === "live") {
        return <LiveApp />;
    }

    return <FixtureApp />;
}

function FixtureApp(): React.JSX.Element {
    const { controller, state } = useRunController(
        fixtureRunClient,
        fixtureAdapter.runs[0]!.session_id,
        fixtureAdapter.workspace.workspace_id,
        fixtureNow,
    );

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
                        <StatusBadge label="연결 대기" tone="neutral" />
                    </div>
                    <section className="settings-summary" aria-labelledby="settings-heading">
                        <h2 id="settings-heading">설정</h2>
                        <p>fixture 기반 화면 · 실제 API 호출 없음</p>
                    </section>
                </header>

                <div className="workspace-grid">
                    <nav className="project-sidebar" aria-label="프로젝트 및 화면">
                        <ProjectPanel canMutate={state.connection === "connected"} />
                        <div className="sidebar-links" aria-label="작업 영역">
                            <a className="sidebar-link sidebar-link-active" href="#screen-chat">
                                대화
                            </a>
                            <a className="sidebar-link" href="#screen-pointers">
                                등록 자료
                            </a>
                            <a className="sidebar-link" href="#screen-settings">
                                모델·예산
                            </a>
                        </div>
                    </nav>

                    <main id="main-content" className="conversation" tabIndex={-1}>
                        <div className="conversation-heading">
                            <div>
                                <p className="eyebrow">대화 · 코드 작업</p>
                                <h2>계약 fixture 화면</h2>
                            </div>
                            <StatusBadge label="미리보기" tone="neutral" />
                        </div>
                        <div className="feature-stack">
                            <ConnectionPanel />
                            <ConversationPanel controller={controller} state={state} />
                            <ApprovalCard controller={controller} state={state} />
                        </div>
                    </main>

                    <aside className="context-sidebar" aria-label="컨텍스트와 포인터">
                        <ContextPanel />
                        <PointerPanel canMutate={state.connection === "connected"} />
                        <PointerReadPanel canRead={state.connection === "connected"} />
                        <PdfParsePanel canMutate={state.connection === "connected"} />
                        <SettingsPanel />
                    </aside>
                </div>
            </div>
        </>
    );
}
