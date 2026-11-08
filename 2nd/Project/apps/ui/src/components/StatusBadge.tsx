/** Text-first status badge whose meaning does not depend on color alone. */
export interface StatusBadgeProps {
    label: string;
    tone: "neutral" | "success" | "warning" | "danger";
}

export function StatusBadge({ label, tone }: StatusBadgeProps): React.JSX.Element {
    return <span className={`status-badge status-${tone}`}>{label}</span>;
}
