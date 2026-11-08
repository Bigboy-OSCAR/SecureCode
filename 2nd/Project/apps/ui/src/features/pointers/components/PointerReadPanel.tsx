/** Renders a bounded, provenance-backed pointer read as a separate screen. */
import { Alert, Button } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";
import { usePointerReadWorkflow } from "../hooks/usePointerReadWorkflow.js";

const rangeLabels: Record<string, string> = {
    byte: "바이트 범위",
    line: "줄 범위",
    section: "문서 구역",
    json_path: "JSON 경로",
    pdf_page: "페이지",
};

export interface PointerReadPanelProps {
    canRead: boolean;
}

export function PointerReadPanel({ canRead }: PointerReadPanelProps): React.JSX.Element {
    const reading = fixtureAdapter.pointerRead;
    const workflow = usePointerReadWorkflow();

    return (
        <section className="feature-card" aria-labelledby="pointer-read-heading" data-testid="screen-pointer-read">
            <div className="feature-heading">
                <h2 id="pointer-read-heading">부분 읽기 · 출처</h2>
                <span>{reading.provenance.display_name ?? "등록 자료"}</span>
            </div>
            <p>
                반환 범위 {rangeLabels[reading.provenance.selection?.range.type ?? ""] ?? "확인 불가"} · 버전{" "}
                {reading.provenance.revision} · {reading.truncated ? "일부 반환됨" : "끝"}
            </p>
            <pre className="bounded-code" data-testid="bounded-source-preview">
                {boundedPreview(reading.content, 120)}
            </pre>
            {reading.next_cursor ? (
                <Button type="button" disabled={!canRead} onClick={workflow.readNext} data-testid="read-next">
                    다음 부분
                </Button>
            ) : null}
            {workflow.nextMessage ? <p role="status">{workflow.nextMessage}</p> : null}
            {!canRead ? <p role="status">연결 복구 후 범위를 다시 조회하세요.</p> : null}
            <Alert title="원본이 변경됐습니다" variant="warning">
                {fixtureAdapter.pointerSourceChanged.error.message}
            </Alert>
            <Alert title="자료 보관 기간이 끝났습니다" variant="warning">
                {fixtureAdapter.pointerExpired.error.message}
            </Alert>
            <Alert title="이 범위가 입력 예산을 넘었습니다" variant="warning">
                {fixtureAdapter.pointerBudgetExceeded.error.message}
            </Alert>
            <Alert title="범위 입력을 확인하세요" variant="error">
                {fixtureAdapter.pointerSelectorError.error.message}
            </Alert>
            <details>
                <summary>읽기 중·빈 결과·검색 무결과 상태</summary>
                <p role="status">요청한 범위를 읽는 중…</p>
                <p>이 범위에 표시할 텍스트가 없습니다.</p>
                <p>일치하는 내용을 찾지 못했습니다.</p>
            </details>
        </section>
    );
}
