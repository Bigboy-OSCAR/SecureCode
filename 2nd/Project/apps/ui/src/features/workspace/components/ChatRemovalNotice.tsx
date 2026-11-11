import { Button } from "../../../components/index.js";
import type { DeskWorkspaceState } from "../hooks/useDeskWorkspace.js";

export function ChatRemovalNotice({ state }: { state: DeskWorkspaceState }): React.JSX.Element | null {
    if (!state.deletedChat) return null;
    return (
        <div className="desk-deletion-notice" role="status">
            <span>대화를 삭제했습니다.</span>
            <Button variant="quiet" disabled={state.busy} onClick={() => void state.undoChatRemoval()}>
                실행 취소
            </Button>
            <button className="desk-icon-button" aria-label="삭제 알림 닫기" onClick={state.dismissChatRemoval}>
                ×
            </button>
        </div>
    );
}
