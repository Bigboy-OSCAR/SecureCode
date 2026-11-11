/**
 * Native modal dialog with managed open state and a caller-provided close request.
 * Focus starts on the title (never on a confirming button) and returns to the opener on close;
 * when the opener is gone (e.g. its card was replaced) it goes to `returnFocusId` instead.
 */
import { useEffect, useRef, type PropsWithChildren } from "react";

export interface ModalProps extends PropsWithChildren {
    open: boolean;
    title: string;
    onRequestClose: () => void;
    /** Element to focus on close when the button that opened the dialog no longer exists. */
    returnFocusId?: string;
}

export function Modal({ open, title, onRequestClose, returnFocusId, children }: ModalProps): React.JSX.Element | null {
    const dialogRef = useRef<HTMLDialogElement>(null);
    const titleRef = useRef<HTMLHeadingElement>(null);

    useEffect(() => {
        const dialog = dialogRef.current;
        if (!open || !dialog) {
            return;
        }
        const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        if (!dialog.open) {
            dialog.showModal();
        }
        titleRef.current?.focus();
        return () => {
            if (dialog.open) {
                dialog.close();
            }
            const target = opener?.isConnected ? opener : returnFocusId ? document.getElementById(returnFocusId) : null;
            target?.focus();
        };
    }, [open, returnFocusId]);

    if (!open) {
        return null;
    }

    return (
        <dialog
            className="modal"
            ref={dialogRef}
            aria-labelledby="modal-title"
            onCancel={(event) => {
                event.preventDefault();
                onRequestClose();
            }}
        >
            <div className="modal-header">
                <h2 id="modal-title" ref={titleRef} tabIndex={-1}>
                    {title}
                </h2>
                <button className="modal-close" type="button" aria-label="대화상자 닫기" onClick={onRequestClose}>
                    닫기
                </button>
            </div>
            <div className="modal-content">{children}</div>
        </dialog>
    );
}
