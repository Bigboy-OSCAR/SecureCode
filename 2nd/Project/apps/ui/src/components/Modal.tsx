/** Native modal dialog with managed open state and a caller-provided close request. */
import { useEffect, useRef, type PropsWithChildren } from "react";

export interface ModalProps extends PropsWithChildren {
    open: boolean;
    title: string;
    onRequestClose: () => void;
}

export function Modal({ open, title, onRequestClose, children }: ModalProps): React.JSX.Element | null {
    const dialogRef = useRef<HTMLDialogElement>(null);

    useEffect(() => {
        const dialog = dialogRef.current;
        if (!dialog) {
            return;
        }

        if (open && !dialog.open) {
            dialog.showModal();
        } else if (!open && dialog.open) {
            dialog.close();
        }
    }, [open]);

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
                <h2 id="modal-title">{title}</h2>
                <button className="modal-close" type="button" aria-label="대화상자 닫기" onClick={onRequestClose}>
                    닫기
                </button>
            </div>
            <div className="modal-content">{children}</div>
        </dialog>
    );
}
