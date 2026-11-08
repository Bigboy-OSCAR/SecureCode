/** Displays PDF parsing progress, partial failures, expiry, and source changes. */
import type { PdfJobStatus } from "@securecode/contracts";
import { useState, type FormEvent } from "react";
import { Alert, Button, InputField, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { isPdfPathValid } from "../model/pointerForm.js";

export function PdfParsePanel(): React.JSX.Element {
    const [pdfPath, setPdfPath] = useState("");
    const [submitted, setSubmitted] = useState(false);
    const job = fixtureAdapter.pdfJobs.find((status) => status.state === "partial");
    if (!job || job.state !== "partial") {
        throw new Error("The partial PDF fixture is missing.");
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault();
        if (isPdfPathValid(pdfPath)) {
            setSubmitted(true);
        }
    }

    return (
        <section className="feature-card" aria-labelledby="pdf-heading" data-testid="screen-pdf">
            <div className="feature-heading">
                <h2 id="pdf-heading">PDF 텍스트 추출</h2>
                <StatusBadge label={getPdfStateLabel(job.state)} tone="warning" />
            </div>
            <p>
                페이지 {job.page_count}개 중 {job.excluded_pages.length}개 제외
            </p>
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
            <div className="state-picker" role="group" aria-label="PDF 계약 상태">
                {fixtureAdapter.pdfJobs.map((status) => (
                    <StatusBadge
                        key={`${status.job_id}-${status.state}`}
                        label={getPdfStateLabel(status.state)}
                        tone="neutral"
                    />
                ))}
            </div>
            {fixtureAdapter.pdfJobs.filter(isStalePdfJob).map((status) => (
                <Alert key={status.job_id} title="원본이 변경되어 이전 추출을 사용할 수 없습니다" variant="warning">
                    {status.reason === "source_changed"
                        ? "원본을 확인한 뒤 다시 처리하세요."
                        : "처리기를 확인한 뒤 다시 처리하세요."}
                </Alert>
            ))}
            <form onSubmit={handleSubmit} className="stack-form">
                <InputField
                    id="pdf-path"
                    label="로컬 PDF 경로"
                    value={pdfPath}
                    maxLength={4096}
                    onChange={(event) => {
                        setPdfPath(event.currentTarget.value);
                        setSubmitted(false);
                    }}
                    data-testid="pdf-path"
                />
                <Button type="submit" disabled={!isPdfPathValid(pdfPath)} data-testid="pdf-parse">
                    등록 후 텍스트 추출 예시
                </Button>
            </form>
            {submitted ? (
                <p role="status">PDF 입력을 확인했습니다. 실제 파일을 읽거나 추출 요청을 보내지 않았습니다.</p>
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
