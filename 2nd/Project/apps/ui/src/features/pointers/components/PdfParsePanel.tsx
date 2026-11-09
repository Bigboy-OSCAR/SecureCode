/** Displays PDF parsing progress, partial failures, expiry, and source changes. */
import type { PdfJobStatus } from "@securecode/contracts";
import { Alert, Button, InputField, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { usePdfWorkflow } from "../hooks/usePdfWorkflow.js";

export interface PdfParsePanelProps {
    canMutate: boolean;
}

export function PdfParsePanel({ canMutate }: PdfParsePanelProps): React.JSX.Element {
    const workflow = usePdfWorkflow();
    const { job } = workflow;

    return (
        <section className="feature-card" aria-labelledby="pdf-heading" data-testid="screen-pdf">
            <div className="feature-heading">
                <h2 id="pdf-heading">PDF 텍스트 추출</h2>
                <StatusBadge label={getPdfStateLabel(job.state)} tone="warning" />
            </div>
            {job.state === "ready" || job.state === "partial" ? (
                <p>
                    페이지 {job.page_count}개{job.state === "partial" ? ` 중 ${job.excluded_pages.length}개 제외` : ""}
                </p>
            ) : (
                <p>페이지 정보를 확인하는 중입니다.</p>
            )}
            {job.state === "partial" ? (
                <ul className="compact-list">
                    {job.excluded_pages.map((page) => (
                        <li key={page.page}>
                            {page.page}쪽 ·{" "}
                            {page.reason === "empty_page"
                                ? "텍스트 없음"
                                : page.reason === "scanned_page"
                                  ? "스캔 이미지"
                                  : "페이지 읽기 실패"}
                        </li>
                    ))}
                </ul>
            ) : null}
            <div className="state-picker" role="group" aria-label="PDF 계약 상태">
                {fixtureAdapter.pdfJobs.map((status, position) => (
                    <Button
                        key={`${status.job_id}-${status.state}`}
                        type="button"
                        variant={workflow.selectedPosition === position ? "primary" : "secondary"}
                        aria-pressed={workflow.selectedPosition === position}
                        onClick={() => workflow.selectJob(position)}
                        data-testid={`pdf-state-${status.state}`}
                    >
                        {getPdfStateLabel(status.state)}
                    </Button>
                ))}
            </div>
            {fixtureAdapter.pdfJobs.filter(isStalePdfJob).map((status) => (
                <Alert key={status.job_id} title="원본이 변경되어 이전 추출을 사용할 수 없습니다" variant="warning">
                    {status.reason === "source_changed"
                        ? "원본을 확인한 뒤 다시 처리하세요."
                        : "처리기를 확인한 뒤 다시 처리하세요."}
                </Alert>
            ))}
            <form onSubmit={workflow.submit} className="stack-form">
                <InputField
                    id="pdf-path"
                    label="로컬 PDF 경로"
                    value={workflow.path}
                    maxLength={4096}
                    disabled={!canMutate}
                    onChange={(event) => workflow.setPath(event.currentTarget.value)}
                    data-testid="pdf-path"
                />
                <Button type="submit" disabled={!canMutate || !workflow.canSubmit} data-testid="pdf-parse">
                    등록 후 텍스트 추출 예시
                </Button>
            </form>
            {!canMutate ? <p role="status">연결을 복구한 뒤 PDF 처리 상태를 다시 확인하세요.</p> : null}
            {workflow.submitted ? (
                <p role="status">PDF 경로 형식만 확인했습니다. 실제 파일을 읽거나 추출 요청을 보내지 않았습니다.</p>
            ) : null}
            <details>
                <summary>등록한 PDF가 없는 경우</summary>
                <p>텍스트가 포함된 PDF 경로를 입력하세요.</p>
            </details>
            <p className="muted-copy">텍스트 PDF만 지원합니다. 스캔 문서 OCR이나 원본 업로드는 수행하지 않습니다.</p>
        </section>
    );
}

function isStalePdfJob(status: PdfJobStatus): status is Extract<PdfJobStatus, { state: "stale" }> {
    return status.state === "stale";
}

function getPdfStateLabel(state: PdfJobStatus["state"]): string {
    switch (state) {
        case "queued":
            return "처리 대기";
        case "running":
            return "텍스트 추출 중";
        case "ready":
            return "완료";
        case "partial":
            return "일부 페이지 제외";
        case "failed":
            return "실패";
        case "stale":
            return "원본 변경됨";
        case "unsupported":
            return "지원하지 않는 PDF";
    }
}
