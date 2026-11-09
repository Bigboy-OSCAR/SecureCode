import { Alert, StatusBadge } from "../../../components/index.js";

export function LiveFeatureReadiness(): React.JSX.Element {
    return (
        <>
            <section className="feature-card" aria-labelledby="context-heading" data-testid="screen-context">
                <div className="feature-heading">
                    <h2 id="context-heading">관련 코드 · 출처</h2>
                    <StatusBadge label="준비되지 않음" tone="warning" />
                </div>
                <Alert title="R0 색인 API가 아직 연결되지 않았습니다" variant="warning">
                    작업 3.6이 완료되기 전에는 검색이나 컨텍스트 선택을 요청하지 않습니다.
                </Alert>
            </section>
            <section
                className="feature-card"
                id="screen-pointers"
                aria-labelledby="pointer-heading"
                data-testid="screen-pointers"
            >
                <div className="feature-heading">
                    <h2 id="pointer-heading">등록 자료 · 실행 결과</h2>
                    <StatusBadge label="준비되지 않음" tone="warning" />
                </div>
                <p>Source Pointer, Runtime Pointer, 부분 읽기와 PDF API는 아직 연결되지 않았습니다.</p>
                <p>이 화면은 자료 등록·삭제·읽기를 수행하지 않습니다.</p>
            </section>
            <section
                className="feature-card"
                id="screen-settings"
                aria-labelledby="settings-heading"
                data-testid="screen-settings"
            >
                <div className="feature-heading">
                    <h2 id="settings-heading">모델·예산</h2>
                    <StatusBadge label="호스트 관리" tone="neutral" />
                </div>
                <p>provider 자격 증명과 내부 서비스 토큰은 브라우저에서 입력하거나 보관하지 않습니다.</p>
            </section>
        </>
    );
}
