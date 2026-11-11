/** Project registration with a native folder picker when the desktop bridge is available. */
import { useEffect, useRef, useState } from "react";
import { Alert, Button, InputField, Modal } from "../../../components/index.js";
import { DeskIcon } from "../../../components/DeskIcon.js";
import { formatApiFailure } from "../../../api/apiErrors.js";

type FolderWindow = Window & {
    webkit?: { messageHandlers?: { selectFolder?: { postMessage: (value: { requestId: string }) => void } } };
};
interface Props {
    open: boolean;
    connected: boolean;
    onClose: () => void;
    onRegister: (name: string, path: string) => Promise<void>;
}
export function ProjectDialog({ open, connected, onClose, onRegister }: Props): React.JSX.Element {
    const [name, setName] = useState("");
    const [path, setPath] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const pending = useRef<string | null>(null);
    useEffect(() => {
        const receive = (event: Event): void => {
            if (!(event instanceof CustomEvent)) return;
            const detail: unknown = event.detail;
            if (
                typeof detail !== "object" ||
                !detail ||
                !("requestId" in detail) ||
                detail.requestId !== pending.current
            )
                return;
            pending.current = null;
            if ("path" in detail && typeof detail.path === "string") {
                setPath(detail.path);
                setName(detail.path.split("/").filter(Boolean).at(-1) ?? "");
            }
        };
        window.addEventListener("localdesk:folder-selected", receive);
        return () => window.removeEventListener("localdesk:folder-selected", receive);
    }, []);
    const choose = (): void => {
        const bridge = (window as FolderWindow).webkit?.messageHandlers?.selectFolder;
        if (bridge) {
            pending.current = crypto.randomUUID();
            bridge.postMessage({ requestId: pending.current });
        } else document.getElementById("project-root-path")?.focus();
    };
    const submit = async (): Promise<void> => {
        setBusy(true);
        setError(null);
        try {
            await onRegister(name.trim(), path.trim());
            setName("");
            setPath("");
            onClose();
        } catch (failure) {
            setError(formatApiFailure(failure, "프로젝트를 만들지 못했습니다."));
        } finally {
            setBusy(false);
        }
    };
    return (
        <Modal open={open} title="새 프로젝트" onRequestClose={onClose}>
            <form
                className="desk-project-form"
                onSubmit={(event) => {
                    event.preventDefault();
                    void submit();
                }}
            >
                <p className="muted-copy">작업할 로컬 폴더를 프로젝트로 연결하세요.</p>
                <div className="desk-folder-select">
                    <InputField
                        id="project-root-path"
                        label="프로젝트 폴더"
                        placeholder="로컬 폴더 경로를 입력하세요"
                        value={path}
                        onChange={(event) => {
                            const value = event.currentTarget.value;
                            setPath(value);
                            if (!name) setName(value.split("/").filter(Boolean).at(-1) ?? "");
                        }}
                        data-testid="project-path"
                    />
                    <Button type="button" onClick={choose}>
                        폴더 선택
                    </Button>
                </div>
                <InputField
                    id="project-display-name"
                    label="프로젝트 이름"
                    placeholder="폴더를 선택하면 이름이 자동으로 채워져요"
                    value={name}
                    onChange={(event) => setName(event.currentTarget.value)}
                    maxLength={120}
                    data-testid="project-name"
                />
                <p className="muted-copy">폴더를 선택한 뒤에도 이름을 수정할 수 있어요.</p>
                <div className="desk-local-notice">
                    <DeskIcon name="5_172-imgIconShield" />
                    <p>
                        선택한 폴더를 기준으로 대화합니다.
                        <br />
                        파일과 대화는 이 기기에 저장됩니다.
                    </p>
                </div>
                {!connected ? <p role="status">연결 설정에서 로컬 서비스에 먼저 연결하세요.</p> : null}
                {error ? (
                    <Alert title="프로젝트를 확인하세요" variant="error">
                        {error}
                    </Alert>
                ) : null}
                <div className="desk-modal-actions">
                    <Button type="button" variant="quiet" onClick={onClose}>
                        취소
                    </Button>
                    <Button
                        type="submit"
                        variant="primary"
                        disabled={busy || !connected || !name.trim() || !path.trim()}
                        data-testid="project-register"
                    >
                        {busy ? "만드는 중…" : "프로젝트 만들기"}
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
