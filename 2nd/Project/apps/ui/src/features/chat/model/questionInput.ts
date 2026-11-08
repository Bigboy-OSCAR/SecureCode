export function shouldSubmitQuestionOnEnter(
    key: string,
    shiftKey: boolean,
    isComposing: boolean,
    keyCode: number,
): boolean {
    return key === "Enter" && !shiftKey && !isComposing && keyCode !== 229;
}
