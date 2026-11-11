/** Copies only the answer displayed by the host, with an explicit clipboard failure state. */
import { useState } from "react";
import { DeskIcon } from "../../../components/DeskIcon.js";
export function CopyAnswer({ text, label = "복사" }: { text: string; label?: string }): React.JSX.Element {
    const [status, setStatus] = useState("");
    const copy = async (): Promise<void> => {
        try {
            await navigator.clipboard.writeText(text);
            setStatus("복사됨");
        } catch {
            setStatus("복사하지 못했습니다. 답변 텍스트를 선택해 복사하세요.");
        }
    };
    return (
        <div className="desk-copy-answer">
            <button type="button" onClick={() => void copy()}>
                <DeskIcon name="imgIconCopy1" />
                {label}
            </button>
            <span role="status">{status}</span>
        </div>
    );
}
