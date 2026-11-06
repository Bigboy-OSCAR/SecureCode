/** Composes the stable top-level project, conversation, context, pointer, and settings regions. */
import { Alert, StatusBadge } from "../components/index.js";

export function App(): React.JSX.Element {
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
                        <p>로컬 서비스와 모델 연결 상태</p>
                    </section>
                </header>

                <div className="workspace-grid">
                    <nav className="project-sidebar" aria-label="프로젝트 선택">
                        <h1>프로젝트</h1>
                        <p className="section-placeholder">등록된 프로젝트가 여기에 표시됩니다.</p>
                        <div className="sidebar-links" aria-label="작업 영역">
                            <span className="sidebar-link sidebar-link-active" aria-current="page">
                                대화
                            </span>
                            <span className="sidebar-link">등록 자료</span>
                            <span className="sidebar-link">실행 결과</span>
                        </div>
                    </nav>

                    <main id="main-content" className="conversation" tabIndex={-1}>
                        <div className="conversation-heading">
                            <div>
                                <p className="eyebrow">대화 · 코드 작업</p>
                                <h2>프로젝트를 선택해 시작하세요</h2>
                            </div>
                            <StatusBadge label="프로젝트 없음" tone="neutral" />
                        </div>
                        <Alert title="아직 선택된 프로젝트가 없습니다." variant="info">
                            왼쪽에서 프로젝트를 선택하면 대화와 관련 코드를 확인할 수 있습니다.
                        </Alert>
                        <div className="conversation-empty" aria-label="대화 영역">
                            <span className="empty-icon" aria-hidden="true">
                                ◇
                            </span>
                            <p>대화 내용이 여기에 표시됩니다.</p>
                        </div>
                    </main>

                    <aside className="context-sidebar" aria-label="컨텍스트와 포인터">
                        <section aria-labelledby="context-heading">
                            <div className="panel-heading">
                                <h2 id="context-heading">관련 코드</h2>
                                <StatusBadge label="대기 중" tone="neutral" />
                            </div>
                            <p className="section-placeholder">선택한 코드와 출처가 여기에 표시됩니다.</p>
                        </section>
                        <section aria-labelledby="pointers-heading">
                            <div className="panel-heading">
                                <h2 id="pointers-heading">등록 자료 · 실행 결과</h2>
                            </div>
                            <p className="section-placeholder">등록 자료와 저장된 실행 결과가 여기에 표시됩니다.</p>
                        </section>
                    </aside>
                </div>
            </div>
        </>
    );
}
