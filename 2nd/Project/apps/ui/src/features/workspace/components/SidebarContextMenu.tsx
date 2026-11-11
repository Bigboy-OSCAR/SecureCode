import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface SidebarMenuTarget {
    x: number;
    y: number;
    trigger: HTMLButtonElement;
}
interface Props {
    target: SidebarMenuTarget;
    label: string;
    actionLabel: string;
    focusSelector: string;
    disabled: boolean;
    onClose: () => void;
    onRemove: () => Promise<boolean>;
}

export function SidebarContextMenu({
    target,
    label,
    actionLabel,
    focusSelector,
    disabled,
    onClose,
    onRemove,
}: Props): React.JSX.Element {
    const menu = useRef<HTMLDivElement>(null);
    const item = useRef<HTMLButtonElement>(null);
    const [busy, setBusy] = useState(false);
    const [position, setPosition] = useState({ left: target.x, top: target.y });
    useLayoutEffect(() => {
        const rect = menu.current?.getBoundingClientRect();
        if (rect) {
            setPosition({
                left: Math.max(8, Math.min(target.x, window.innerWidth - rect.width - 8)),
                top: Math.max(8, Math.min(target.y, window.innerHeight - rect.height - 8)),
            });
        }
        item.current?.focus({ preventScroll: true });
    }, [target]);
    useEffect(() => {
        const outside = (event: PointerEvent): void => {
            if (event.target instanceof Node && !menu.current?.contains(event.target)) onClose();
        };
        const closeOnScroll = (event: Event): void => {
            // Only dismiss when the project's position moves, not when chat messages auto-scroll.
            if (event.target instanceof Node && event.target.contains(target.trigger)) onClose();
        };
        window.addEventListener("pointerdown", outside);
        window.addEventListener("resize", onClose);
        window.addEventListener("scroll", closeOnScroll, true);
        return () => {
            window.removeEventListener("pointerdown", outside);
            window.removeEventListener("resize", onClose);
            window.removeEventListener("scroll", closeOnScroll, true);
        };
    }, [onClose, target.trigger]);
    const remove = async (): Promise<void> => {
        if (busy) return;
        setBusy(true);
        const focused = document.activeElement;
        const removed = await onRemove();
        setBusy(false);
        onClose();
        if (document.activeElement !== focused && document.activeElement !== document.body) return;
        if (!removed) target.trigger.focus({ preventScroll: true });
        else
            requestAnimationFrame(() => {
                const next =
                    document.querySelector<HTMLButtonElement>(focusSelector) ??
                    document.querySelector<HTMLButtonElement>(".desk-project.selected .desk-project-open") ??
                    document.querySelector<HTMLButtonElement>(".desk-section-label button");
                next?.focus({ preventScroll: true });
            });
    };
    return createPortal(
        <div
            ref={menu}
            className="desk-project-menu"
            role="menu"
            aria-label={label}
            style={position}
            onKeyDown={(event) => {
                if (event.key === "Escape" || event.key === "Tab") {
                    event.preventDefault();
                    onClose();
                    target.trigger.focus({ preventScroll: true });
                } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
                    event.preventDefault();
                    item.current?.focus();
                }
            }}
        >
            <button ref={item} role="menuitem" disabled={busy || disabled} onClick={() => void remove()}>
                <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    aria-hidden="true"
                >
                    <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7" />
                </svg>
                {busy ? "삭제 중…" : actionLabel}
            </button>
        </div>,
        document.body,
    );
}
