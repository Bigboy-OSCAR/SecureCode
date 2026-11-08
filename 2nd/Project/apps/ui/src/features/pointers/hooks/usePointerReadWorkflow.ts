import { useState } from "react";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";

export function usePointerReadWorkflow(): {
    readNext: () => void;
    nextMessage: string | null;
} {
    const [nextMessage, setNextMessage] = useState<string | null>(null);

    return {
        readNext: () => {
            if (fixtureAdapter.pointerRead.next_cursor) {
                setNextMessage("다음 부분 fixture 응답이 없어 추가 내용을 표시하지 않았습니다.");
            }
        },
        nextMessage,
    };
}
