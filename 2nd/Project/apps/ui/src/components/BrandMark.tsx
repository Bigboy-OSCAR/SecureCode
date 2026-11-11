/** The same vector mark is used by the UI and the native app icon builder. */
export function BrandMark({ compact = false }: { compact?: boolean }): React.JSX.Element {
    return (
        <img
            className="desk-icon"
            src="/brand/localdesk-mark.svg"
            width={compact ? 24 : 44}
            height={compact ? 16 : 24}
            alt=""
            aria-hidden="true"
        />
    );
}
