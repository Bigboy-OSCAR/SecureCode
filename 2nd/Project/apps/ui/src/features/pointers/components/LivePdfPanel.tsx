import type { PdfJobStatus } from "@securecode/contracts";
import { Alert, Button, StatusBadge } from "../../../components/index.js";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import type { UiPointer } from "../../../api/mappers/pointerMapper.js";
import { useLivePdfWorkflow } from "../hooks/useLivePdfWorkflow.js";

interface LivePdfPanelProps {
    api: ApiHttpClient;
    pointer: UiPointer | null;
    canMutate: boolean;
}

export function LivePdfPanel({ api, pointer, canMutate }: LivePdfPanelProps): React.JSX.Element {
    const workflow = useLivePdfWorkflow(api, pointer);
    const selectedSource = pointer?.kind === "source" ? pointer : null;
    const isPdf = Boolean(
        selectedSource &&
        (selectedSource.media_type.toLocaleLowerCase().includes("pdf") ||
            selectedSource.display_name.toLocaleLowerCase().endsWith(".pdf")),
    );
    const job = workflow.job;

    return (
        <section className="feature-card" aria-labelledby="pdf-heading" data-testid="screen-pdf">
            <div className="feature-heading">
                <h2 id="pdf-heading">PDF parsing job</h2>
                <StatusBadge label={job ? pdfStateLabel(job.state) : "등록 PDF 선택"} tone={pdfTone(job?.state)} />
            </div>
            {!isPdf ? (
                <p role="status">PDF 파싱은 등록된 Source Pointer 중 PDF 파일에 대해서만 가능합니다.</p>
            ) : (
                <>
                    <p>
                        원본 문서: {selectedSource?.display_name} · revision {selectedSource?.revision}
                    </p>
                    <Button
                        type="button"
                        disabled={!canMutate || workflow.busy}
                        onClick={() => void workflow.parse()}
                        data-testid="live-pdf-parse"
                    >
                        {workflow.busy ? "PDF 상태 확인 중…" : "PDF parse job 시작"}
                    </Button>
                </>
            )}
            {job ? <PdfJobDetails job={job} /> : null}
            {workflow.error ? (
                <Alert title="PDF parse job 요청 실패" variant="error">
                    {workflow.error}
                </Alert>
            ) : null}
            {!canMutate ? <p role="status">연결 복구 후 PDF 상태를 확인하세요.</p> : null}
        </section>
    );
}

export function PdfJobDetails({ job }: { job: PdfJobStatus }): React.JSX.Element {
    switch (job.state) {
        case "queued":
        case "running":
            return (
                <p role="status">
                    {pdfStateLabel(job.state)} · job {job.job_id} · 추출 텍스트는 이 상태 응답에 포함되지 않습니다.
                </p>
            );
        case "ready":
            return (
                <div>
                    <p>
                        ready · 원본 {job.page_count}쪽 · parser {job.parser_version} · sha256{" "}
                        {job.content_sha256.slice(0, 12)}…
                    </p>
                    <p>페이지 본문은 Source 부분 읽기에서 페이지 범위를 지정해 조회하세요.</p>
                </div>
            );
        case "partial":
            return (
                <div>
                    <p>일부 페이지 제외 · 원본 {job.page_count}쪽</p>
                    <ul className="compact-list">
                        {job.excluded_pages.map((page) => (
                            <li key={`${page.page}-${page.reason}`}>
                                원본 {page.page}쪽 · {pdfExcludedReason(page.reason)}
                            </li>
                        ))}
                    </ul>
                </div>
            );
        case "unsupported":
            return (
                <Alert title="지원하지 않는 PDF" variant="warning">
                    {unsupportedReason(job.reason)} · OCR과 암호 해제는 수행하지 않습니다.
                </Alert>
            );
        case "failed":
            return (
                <Alert title="PDF parsing failed" variant="error">
                    {failedReason(job.reason)}
                </Alert>
            );
        case "stale":
            return (
                <Alert title="PDF 원본 또는 parser가 변경됨" variant="warning">
                    {job.reason === "source_changed"
                        ? "원본 Source를 갱신한 뒤 다시 파싱하세요."
                        : "현재 parser로 다시 파싱하세요."}
                </Alert>
            );
    }
}

function pdfStateLabel(state: PdfJobStatus["state"]): string {
    switch (state) {
        case "queued":
            return "queued · 처리 대기";
        case "running":
            return "running · parsing";
        case "ready":
            return "ready";
        case "partial":
            return "일부 페이지 제외";
        case "unsupported":
            return "unsupported";
        case "failed":
            return "failed";
        case "stale":
            return "source_changed";
    }
}

function pdfTone(state: PdfJobStatus["state"] | undefined): "neutral" | "success" | "warning" | "danger" {
    if (state === "ready") {
        return "success";
    }
    if (state === "failed") {
        return "danger";
    }
    return state === "unsupported" || state === "stale" || state === "partial" ? "warning" : "neutral";
}

function pdfExcludedReason(reason: "empty_page" | "scanned_page" | "unreadable_page"): string {
    switch (reason) {
        case "empty_page":
            return "텍스트 없음";
        case "scanned_page":
            return "스캔 이미지, OCR 미지원";
        case "unreadable_page":
            return "페이지 읽기 실패";
    }
}

function unsupportedReason(reason: Extract<PdfJobStatus, { state: "unsupported" }>["reason"]): string {
    switch (reason) {
        case "scanned_document":
            return "스캔 PDF";
        case "empty_document":
            return "추출 가능한 텍스트 없음";
        case "encrypted":
            return "암호화 PDF";
        case "page_limit":
            return "페이지 한도 초과";
        case "size_limit":
            return "파일 크기 한도 초과";
        case "unsupported_format":
            return "지원하지 않는 형식";
    }
}

function failedReason(reason: Extract<PdfJobStatus, { state: "failed" }>["reason"]): string {
    switch (reason) {
        case "damaged":
            return "손상된 PDF입니다.";
        case "timeout":
            return "처리 시간 한도를 초과했습니다.";
        case "parse_failed":
            return "PDF 파서에서 오류가 발생했습니다.";
    }
}
