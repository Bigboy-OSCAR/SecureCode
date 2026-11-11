/** Below 1024px only one side panel is expanded at a time; the conversation and approvals stay visible. */
export type SidePanel = "project" | "context";

interface PanelSwitcherProps {
    open: SidePanel | null;
    onToggle: (panel: SidePanel) => void;
}

const panels: { id: SidePanel; label: string; controls: string }[] = [
    { id: "project", label: "프로젝트 패널", controls: "project-panel" },
    { id: "context", label: "자료·예산 패널", controls: "context-panel" },
];

export function PanelSwitcher({ open, onToggle }: PanelSwitcherProps): React.JSX.Element {
    return (
        <div className="panel-switcher" role="group" aria-label="패널 전환">
            {panels.map((panel) => (
                <button
                    key={panel.id}
                    type="button"
                    className="panel-toggle"
                    aria-expanded={open === panel.id}
                    aria-controls={panel.controls}
                    onClick={() => {
                        const opening = open !== panel.id;
                        onToggle(panel.id);
                        // The context panel sits after the conversation in a narrow layout; bring it into view.
                        if (opening) {
                            requestAnimationFrame(() =>
                                document.getElementById(panel.controls)?.scrollIntoView({ block: "start" }),
                            );
                        }
                    }}
                    data-testid={`panel-toggle-${panel.id}`}
                >
                    {panel.label} {open === panel.id ? "접기" : "펼치기"}
                </button>
            ))}
        </div>
    );
}

export function panelClass(base: string, panel: SidePanel, open: SidePanel | null): string {
    return `${base} side-panel${open === panel ? " side-panel-open" : ""}`;
}
