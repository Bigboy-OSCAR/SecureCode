/** Empty conversation state from the Figma new-project screen. */
import { DeskIcon } from "../../../components/DeskIcon.js";
export function DeskWelcome({
    name,
    path,
    onSuggestion,
}: {
    name: string | null;
    path?: string;
    onSuggestion?: (value: string) => void;
}): React.JSX.Element {
    return (
        <div className="desk-welcome">
            <div className="desk-welcome-icon">
                <DeskIcon name="6_256-imgIconFolder" />
            </div>
            <h1>{name ? "이 폴더에서 시작해 볼까요?" : "내 폴더에서, 내 모델로."}</h1>
            <p>
                {name
                    ? `${name} 폴더를 기반으로 대화를 시작합니다.`
                    : "프로젝트를 추가하고 로컬 모델과 대화를 시작하세요."}
            </p>
            {name ? (
                <p className="desk-welcome-path">
                    <DeskIcon name="6_256-imgIconFolder1" />
                    {path ?? name}
                </p>
            ) : null}
            {onSuggestion ? (
                <div className="desk-suggestions">
                    {["폴더 내용 요약하기", "문서에서 핵심 찾기", "아이디어 함께 정리하기"].map((label) => (
                        <button key={label} onClick={() => onSuggestion(label)}>
                            {label}
                        </button>
                    ))}
                </div>
            ) : null}
        </div>
    );
}
