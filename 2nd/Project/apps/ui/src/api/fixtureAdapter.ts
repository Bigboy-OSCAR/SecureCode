/** Supplies contract-backed examples to the UI without making network requests. */
import type {
    AppEvent,
    ApprovalDecisionResponse,
    BootstrapResponse,
    ContextPreviewResponse,
    ErrorResponse,
    IndexStatusResponse,
    PdfJobStatus,
    PointerDescriptor,
    PointerListResult,
    PointerReadResult,
    RunListResponse,
    RunSnapshot,
    SettingsResponse,
    SymbolBundle,
    SymbolSearchResponse,
    Workspace,
    WorkspaceListResponse,
} from "@securecode/contracts";
import approvalExpiredFixture from "../../../../contracts/fixtures/api/approval-expired-error.valid.json";
import approvalDigestErrorFixture from "../../../../contracts/fixtures/api/approval-digest-mismatch-error.valid.json";
import bootstrapExpiredFixture from "../../../../contracts/fixtures/api/bootstrap-code-expired-error.valid.json";
import bootstrapResponseFixture from "../../../../contracts/fixtures/api/bootstrap-response.valid.json";
import healthPreauthFixture from "../../../../contracts/fixtures/api/health-preauth-minimal.valid.json";
import indexIndexingFixture from "../../../../contracts/fixtures/api/index-status-indexing.valid.json";
import indexPartialFixture from "../../../../contracts/fixtures/api/index-status-partial.valid.json";
import indexReadyFixture from "../../../../contracts/fixtures/api/index-status-ready.valid.json";
import indexStaleFixture from "../../../../contracts/fixtures/api/index-status-stale.valid.json";
import indexZeroFilesFixture from "../../../../contracts/fixtures/api/index-status-zero-files.valid.json";
import runAlreadyActiveFixture from "../../../../contracts/fixtures/api/run-already-active-error.valid.json";
import runAwaitingFixture from "../../../../contracts/fixtures/api/run-snapshot-awaiting-approval.valid.json";
import runCancelledFixture from "../../../../contracts/fixtures/api/run-snapshot-cancelled.valid.json";
import runCompletedFixture from "../../../../contracts/fixtures/api/run-snapshot-completed.valid.json";
import runListFixture from "../../../../contracts/fixtures/api/run-list.valid.json";
import settingsFixture from "../../../../contracts/fixtures/api/settings-not-configured.valid.json";
import protectionUnavailableFixture from "../../../../contracts/fixtures/api/protection-unavailable-error.valid.json";
import workspaceFixture from "../../../../contracts/fixtures/api/workspace.valid.json";
import workspaceEmptyFixture from "../../../../contracts/fixtures/api/workspace-list-page.valid.json";
import workspacePathErrorFixture from "../../../../contracts/fixtures/api/workspace-path-rejected-error.valid.json";
import contextBudgetFixture from "../../../../contracts/fixtures/context/preview-explicit-over-budget.valid.json";
import contextNoMatchFixture from "../../../../contracts/fixtures/context/preview-search-no-match.valid.json";
import contextPreviewFixture from "../../../../contracts/fixtures/context/preview-plan-response.valid.json";
import contextStaleFixture from "../../../../contracts/fixtures/context/preview-stale-error.valid.json";
import outputDeltaFixture from "../../../../contracts/fixtures/events/run-output-delta-korean.valid.json";
import approvalRejectedFixture from "../../../../contracts/fixtures/events/run-approval-rejected.valid.json";
import runStatusCancelledFixture from "../../../../contracts/fixtures/events/run-status-cancelled-terminal.valid.json";
import runStatusRunningFixture from "../../../../contracts/fixtures/events/run-status-running.valid.json";
import approvalDecisionResponseFixture from "../../../../contracts/fixtures/api/approval-decision-response.valid.json";
import symbolBundleFixture from "../../../../contracts/fixtures/symbols/bundle.valid.json";
import symbolNoMatchFixture from "../../../../contracts/fixtures/symbols/search-no-match.valid.json";
import symbolSearchFixture from "../../../../contracts/fixtures/symbols/search-response.valid.json";
import pointerExpiredFixture from "../../../../contracts/fixtures/pointers/error-expired.valid.json";
import pointerForbiddenFixture from "../../../../contracts/fixtures/pointers/error-forbidden-session.valid.json";
import pointerBudgetFixture from "../../../../contracts/fixtures/pointers/error-budget-exceeded.valid.json";
import pointerSelectorErrorFixture from "../../../../contracts/fixtures/pointers/error-invalid-selector.valid.json";
import pointerSourceChangedFixture from "../../../../contracts/fixtures/pointers/error-source-changed.valid.json";
import pdfFailedFixture from "../../../../contracts/fixtures/pointers/pdf-job-failed.valid.json";
import pdfPartialFixture from "../../../../contracts/fixtures/pointers/pdf-job-partial.valid.json";
import pdfQueuedFixture from "../../../../contracts/fixtures/pointers/pdf-job-queued.valid.json";
import pdfReadyFixture from "../../../../contracts/fixtures/pointers/pdf-job-ready.valid.json";
import pdfRunningFixture from "../../../../contracts/fixtures/pointers/pdf-job-running.valid.json";
import pdfStaleFixture from "../../../../contracts/fixtures/pointers/pdf-job-stale.valid.json";
import pdfUnsupportedFixture from "../../../../contracts/fixtures/pointers/pdf-job-unsupported.valid.json";
import pointerListEmptyFixture from "../../../../contracts/fixtures/pointers/pointer-list-empty.valid.json";
import pointerListFixture from "../../../../contracts/fixtures/pointers/pointer-list.valid.json";
import pointerReadFixture from "../../../../contracts/fixtures/pointers/read-selected-utf8.valid.json";
import runtimeDescriptorFixture from "../../../../contracts/fixtures/pointers/pointer-descriptor-runtime.valid.json";

// JSON imports widen literal fields; ui.test.tsx validates each source fixture against its schema.
const bootstrap = bootstrapResponseFixture.data as BootstrapResponse;
const bootstrapExpired = bootstrapExpiredFixture.data as ErrorResponse;
const workspace = workspaceFixture.data as Workspace;
const healthPreauth = healthPreauthFixture.data;
const workspaceListEmpty = workspaceEmptyFixture.data as WorkspaceListResponse;
const workspacePathError = workspacePathErrorFixture.data as ErrorResponse;
const indexStates = [
    indexIndexingFixture.data as IndexStatusResponse,
    indexPartialFixture.data as IndexStatusResponse,
    indexReadyFixture.data as IndexStatusResponse,
    indexZeroFilesFixture.data as IndexStatusResponse,
    indexStaleFixture.data as IndexStatusResponse,
];
const runList = runListFixture.data as RunListResponse;
const runAlreadyActive = runAlreadyActiveFixture.data as ErrorResponse;
const approvalExpired = approvalExpiredFixture.data as ErrorResponse;
const approvalDigestError = approvalDigestErrorFixture.data as ErrorResponse;
const runs = [
    runAwaitingFixture.data as RunSnapshot,
    runCompletedFixture.data as RunSnapshot,
    runCancelledFixture.data as RunSnapshot,
];
const outputDelta = outputDeltaFixture.data as AppEvent;
const approvalRejected = approvalRejectedFixture.data as AppEvent;
const runStatusCancelled = runStatusCancelledFixture.data as AppEvent;
const runStatusRunning = runStatusRunningFixture.data as AppEvent;
const approvalDecisionResponse = approvalDecisionResponseFixture.data as ApprovalDecisionResponse;
const settings = settingsFixture.data as SettingsResponse;
const protectionUnavailable = protectionUnavailableFixture.data as ErrorResponse;
const symbolSearch = symbolSearchFixture.data as SymbolSearchResponse;
const symbolNoMatch = symbolNoMatchFixture.data as SymbolSearchResponse;
const symbolBundle = symbolBundleFixture.data as SymbolBundle;
const pointers = [pointerListFixture.data as PointerListResult, pointerListEmptyFixture.data as PointerListResult];
const runtimeDescriptor = runtimeDescriptorFixture.data as PointerDescriptor;
const pointerRead = pointerReadFixture.data as PointerReadResult;
const pointerExpired = pointerExpiredFixture.data as ErrorResponse;
const pointerForbidden = pointerForbiddenFixture.data as ErrorResponse;
const pointerSourceChanged = pointerSourceChangedFixture.data as ErrorResponse;
const pointerSelectorError = pointerSelectorErrorFixture.data as ErrorResponse;
const pointerBudgetExceeded = pointerBudgetFixture.data as ErrorResponse;
const contextStale = contextStaleFixture.data as ErrorResponse;
const contextPreviews = [
    contextPreviewFixture.data as ContextPreviewResponse,
    contextNoMatchFixture.data as ContextPreviewResponse,
    contextBudgetFixture.data as ContextPreviewResponse,
];
const pdfJobs = [
    pdfQueuedFixture.data as PdfJobStatus,
    pdfRunningFixture.data as PdfJobStatus,
    pdfReadyFixture.data as PdfJobStatus,
    pdfPartialFixture.data as PdfJobStatus,
    pdfFailedFixture.data as PdfJobStatus,
    pdfStaleFixture.data as PdfJobStatus,
    pdfUnsupportedFixture.data as PdfJobStatus,
];

export const fixtureAdapter = {
    bootstrap,
    bootstrapExpired,
    healthPreauth,
    workspace,
    workspaceListEmpty,
    workspacePathError,
    indexStates,
    runList,
    runAlreadyActive,
    runs,
    approvalExpired,
    approvalDigestError,
    outputDelta,
    approvalRejected,
    runStatusCancelled,
    runStatusRunning,
    approvalDecisionResponse,
    settings,
    protectionUnavailable,
    symbolSearch,
    symbolNoMatch,
    symbolBundle,
    pointers,
    runtimeDescriptor,
    pointerRead,
    pointerExpired,
    pointerForbidden,
    pointerSourceChanged,
    pointerSelectorError,
    pointerBudgetExceeded,
    contextStale,
    contextPreviews,
    pdfJobs,
};
