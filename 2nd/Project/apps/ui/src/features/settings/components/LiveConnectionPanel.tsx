import { useState, type FormEvent } from "react";
import type { HealthResponse, SettingsResponse } from "@securecode/contracts";
import { Alert, Button, InputField, StatusBadge } from "../../../components/index.js";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";

export interface LiveConnectionPanelProps {
    api: ApiHttpClient;
    connected: boolean;
    health: HealthResponse | null;
    settings: SettingsResponse | null;
    onAuthenticated: () => void;
    onStatus: (health: HealthResponse, settings: SettingsResponse) => void;
}

export function LiveConnectionPanel({
    api,
    connected,
    health,
    settings,
    onAuthenticated,
    onStatus,
}: LiveConnectionPanelProps): React.JSX.Element {
    const [code, setCode] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
        event.preventDefault();
        const oneTimeCode = code;
        setCode("");
        setError(null);
        setBusy(true);
        try {
            await api.bootstrap({ code: oneTimeCode });
            onAuthenticated();
            const [nextHealth, nextSettings] = await Promise.all([api.getHealth(), api.getSettings()]);
            onStatus(nextHealth, nextSettings);
        } catch (requestError) {
            setError(formatApiFailure(requestError, "로컬 호스트에 연결하지 못했습니다."));
        } finally {
            setBusy(false);
            setCode("");
        }
    };

    return (
        <section className="feature-card" aria-labelledby="connection-heading" data-testid="screen-connection">
            <div className="feature-heading">
                <h2 id="connection-heading">로컬 서비스 연결</h2>
                <StatusBadge
                    label={connected ? "호스트 연결됨" : "연결 대기"}
                    tone={connected ? "success" : "neutral"}
                />
            </div>
            <p>실행 창에 표시된 일회용 연결 코드를 입력하세요. 코드는 same-origin bootstrap 요청에만 사용됩니다.</p>
            <form onSubmit={(event) => void submit(event)} className="stack-form">
                <InputField
                    id="connection-code"
                    label="연결 코드"
                    value={code}
                    maxLength={64}
                    pattern="(?:[A-Za-z0-9]|-){8,64}"
                    onChange={(event) => setCode(event.currentTarget.value)}
                    autoComplete="off"
                    disabled={busy || connected}
                    data-testid="connection-code"
                />
                <Button
                    type="submit"
                    variant="primary"
                    disabled={busy || connected || !/^[A-Za-z0-9-]{8,64}$/.test(code)}
                    data-testid="connect-submit"
                >
                    {busy ? "연결 중…" : connected ? "연결됨" : "연결"}
                </Button>
            </form>
            {error ? (
                <Alert title="연결 상태를 확인하세요" variant="error">
                    {error}
                </Alert>
            ) : null}
            {health ? (
                <div role="status">
                    호스트 상태: {health.status}
                    {health.components?.some((component) => component.status === "unavailable")
                        ? " · 일부 기능 사용 불가"
                        : ""}
                </div>
            ) : null}
            <p className="muted-copy">
                모델 설정은 호스트에서 관리합니다. provider API 키와 내부 서비스 토큰은 브라우저에 전달되지 않습니다.
            </p>
            <p className="muted-copy">{settings ? "호스트 설정 상태 확인됨" : "호스트 설정 확인 전"}</p>
        </section>
    );
}
