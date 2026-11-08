/** Renders Source registration and Runtime result lifecycles as distinct actions. */
import { useState, type FormEvent } from "react";
import { Alert, Button, InputField, Modal, StatusBadge } from "../../../components/index.js";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { boundedPreview } from "../../shared/model/boundedPreview.js";
import { isSourcePathValid } from "../model/pointerForm.js";

type DeleteIntent = "source" | "runtime";

export function PointerPanel(): React.JSX.Element {
    const [intent, setIntent] = useState<DeleteIntent | null>(null);
    const [confirmed, setConfirmed] = useState<DeleteIntent | null>(null);
    const [sourcePath, setSourcePath] = useState("");
    const [registrationSubmitted, setRegistrationSubmitted] = useState(false);
    const source = fixtureAdapter.pointers[0]!.items[0]!;
    const expiredSource = fixtureAdapter.pointers[1]!;
    const runtime = fixtureAdapter.runtimeDescriptor;
    const modalTitle = intent === "source" ? "자료 등록을 해제하시겠습니까?" : "저장 결과를 삭제하시겠습니까?";

    function handleRegister(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault();
        if (isSourcePathValid(sourcePath)) {
            setRegistrationSubmitted(true);
        }
    }

    return (
        <section className="feature-card" aria-labelledby="pointers-heading" data-testid="screen-pointers">
            <div className="feature-heading">
                <h2 id="pointers-heading">등록 자료 · 실행 결과</h2>
                <StatusBadge label="부분 미리보기" tone="neutral" />
            </div>
            <form onSubmit={handleRegister} className="stack-form">
                <InputField
                    id="source-path"
                    label="등록할 자료의 로컬 경로"
                    value={sourcePath}
                    maxLength={4096}
                    onChange={(event) => {
                        setSourcePath(event.currentTarget.value);
                        setRegistrationSubmitted(false);
                    }}
                    data-testid="source-path"
                />
                <Button
                    type="submit"
                    variant="primary"
                    disabled={!isSourcePathValid(sourcePath)}
                    data-testid="source-register"
                >
                    자료 등록 예시
                </Button>
            </form>
            {registrationSubmitted ? (
                <p role="status">자료 등록 입력을 확인했습니다. 실제 파일에 접근하거나 요청을 보내지 않았습니다.</p>
            ) : null}
            <div className="pointer-entry">
                <h3>등록 자료</h3>
                <p>
                    {source.display_name} · {source.byte_size.toLocaleString()} bytes · 버전 {source.revision}
                </p>
                <p>제한 미리보기: {boundedPreview(source.preview, 120)}</p>
                <Button type="button" onClick={() => setIntent("source")} data-testid="source-unregister">
                    등록 해제
                </Button>
                <p className="muted-copy">등록을 해제해도 원본 파일은 유지됩니다.</p>
            </div>
            <div className="pointer-entry">
                <h3>저장 실행 결과</h3>
                <p>저장된 도구 출력 · {runtime.byte_size.toLocaleString()} bytes · 세션 내 임시 보관</p>
                <Button type="button" onClick={() => setIntent("runtime")} data-testid="runtime-delete">
                    저장 결과 삭제
                </Button>
                <p className="muted-copy">실행 결과 삭제는 이미 수행된 명령이나 파일 변경을 되돌리지 않습니다.</p>
            </div>
            {expiredSource.items.length === 0 ? (
                <Alert title="등록 자료가 없습니다" variant="info">
                    자료를 등록하면 안전한 일부 미리보기와 출처를 확인할 수 있습니다.
                </Alert>
            ) : null}
            <details>
                <summary>만료·원본 변경·읽기 오류 예시</summary>
                <Alert title="자료 보관 기간이 끝났습니다" variant="warning">
                    {fixtureAdapter.pointerExpired.error.message}
                </Alert>
                <Alert title="원본 파일이 변경됐습니다" variant="warning">
                    {fixtureAdapter.pointerSourceChanged.error.message}
                </Alert>
                <Alert title="다른 세션의 실행 결과는 볼 수 없습니다" variant="error">
                    {fixtureAdapter.pointerForbidden.error.message}
                </Alert>
                <p>비어 있는 목록은 새 자료를 등록할 수 있으며, 읽기 오류가 나면 원본을 지우지 않고 다시 등록합니다.</p>
            </details>
            {confirmed ? (
                <Alert
                    title={
                        confirmed === "source" ? "등록 해제 의도를 선택했습니다" : "저장 결과 삭제 의도를 선택했습니다"
                    }
                    variant="info"
                >
                    fixture 화면이며 실제 자료나 원본 파일은 삭제되지 않았습니다.
                </Alert>
            ) : null}
            <Modal open={intent !== null} title={modalTitle} onRequestClose={() => setIntent(null)}>
                <p>
                    {intent === "source"
                        ? "등록을 해제하고 파생 캐시를 정리합니다. 원본 파일은 삭제하지 않습니다."
                        : "이 세션에 저장된 실행 결과를 삭제합니다. 이후 읽을 수 없습니다."}
                </p>
                <div className="action-row">
                    <Button
                        type="button"
                        variant="primary"
                        onClick={() => {
                            if (intent) {
                                setConfirmed(intent);
                                setIntent(null);
                            }
                        }}
                        data-testid={intent === "source" ? "source-unregister-confirm" : "runtime-delete-confirm"}
                    >
                        {intent === "source" ? "등록 해제 확인" : "저장 결과 삭제 확인"}
                    </Button>
                    <Button type="button" onClick={() => setIntent(null)} data-testid="pointer-delete-back">
                        돌아가기
                    </Button>
                </div>
            </Modal>
        </section>
    );
}
