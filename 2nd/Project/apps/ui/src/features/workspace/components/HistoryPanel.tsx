/** Read-only previous-conversation panel; continuing explicitly changes the active session. */
import { useEffect, useState } from "react";
import type { RunSnapshot, Session } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import type { DeskChat } from "../hooks/useDeskWorkspace.js";
import { AnswerView } from "../../chat/components/AnswerView.js";
import { formatApiFailure } from "../../../api/apiErrors.js";
import { DeskIcon } from "../../../components/DeskIcon.js";
import { Button, InputField, Modal } from "../../../components/index.js";

interface SearchProps {
    open: boolean;
    chats: DeskChat[];
    onClose: () => void;
    onSelect: (chat: DeskChat) => void;
}
export function SearchDialog({ open, chats, onClose, onSelect }: SearchProps): React.JSX.Element {
    const [query, setQuery] = useState("");
    const results = chats.filter((chat) =>
        `${chat.title} ${chat.runs.map((run) => run.prompt_preview).join(" ")}`
            .toLocaleLowerCase()
            .includes(query.toLocaleLowerCase()),
    );
    return (
        <Modal open={open} title="대화 검색" onRequestClose={onClose}>
            <div className="desk-dialog-stack">
                <div className="desk-search-input">
                    <DeskIcon name="5_1907-imgIconSearch" />
                    <InputField
                        id="chat-search"
                        label="검색어"
                        value={query}
                        onChange={(event) => setQuery(event.currentTarget.value)}
                        placeholder="대화 제목과 질문 검색"
                    />
                </div>
                <p className="muted-copy">검색 결과 {results.length}개</p>
                {results.map((chat) => (
                    <button className="desk-search-result" key={chat.session.session_id} onClick={() => onSelect(chat)}>
                        <strong>{chat.title}</strong>
                        <small>{new Date(chat.session.created_at).toLocaleDateString("ko-KR")}</small>
                        <p>{chat.runs.at(-1)?.prompt_preview ?? "아직 질문이 없습니다."}</p>
                    </button>
                ))}
                <p className="muted-copy">결과를 선택하면 이전 대화 패널에서 열립니다.</p>
            </div>
        </Modal>
    );
}
export function HistoryPanel({
    api,
    chat,
    chats,
    onSelect,
    onClose,
    onContinue,
}: {
    api: ApiHttpClient;
    chat: DeskChat | null;
    chats: DeskChat[];
    onSelect: (chat: DeskChat) => void;
    onClose: () => void;
    onContinue: (session: Session) => void;
}): React.JSX.Element {
    const [runs, setRuns] = useState<RunSnapshot[]>([]);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        let live = true;
        setRuns([]);
        setError(null);
        if (chat)
            void Promise.all(chat.runs.map((run) => api.getRun(run.run_id)))
                .then((items) => {
                    if (live) setRuns(items);
                })
                .catch((failure: unknown) => {
                    if (live) setError(formatApiFailure(failure, "이전 대화를 불러오지 못했습니다."));
                });
        return () => {
            live = false;
        };
    }, [api, chat]);
    return (
        <aside className="desk-history-panel" aria-label="이전 대화">
            <div className="desk-drawer-heading">
                <h2>이전 대화</h2>
                <Button variant="quiet" onClick={onClose}>
                    닫기
                </Button>
            </div>
            <div className="desk-history-content">
                <div className="desk-chat-list">
                    {chats.map((item) => (
                        <button
                            key={item.session.session_id}
                            onClick={() => onSelect(item)}
                            className={chat?.session.session_id === item.session.session_id ? "selected" : ""}
                        >
                            {item.title}
                        </button>
                    ))}
                </div>
                {chat ? <h3>{chat.title}</h3> : <p>이전 대화를 선택하세요.</p>}
                {error ? <p role="alert">{error}</p> : null}
                {runs.map((run) => (
                    <div key={run.run_id}>
                        <div className="desk-user-message">{run.prompt_preview}</div>
                        <AnswerView run={run} />
                    </div>
                ))}
            </div>
            {chat ? (
                <div className="desk-history-footer">
                    <Button variant="primary" onClick={() => onContinue(chat.session)}>
                        이 대화 이어가기
                    </Button>
                </div>
            ) : null}
        </aside>
    );
}
