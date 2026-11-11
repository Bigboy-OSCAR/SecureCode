/** Figma model picker and inventory share the real host model catalog. */
import { useState } from "react";
import { Button, InputField, Modal } from "../../../components/index.js";
import { DeskIcon } from "../../../components/DeskIcon.js";
import type { useDeskModels } from "../hooks/useDeskModels.js";
export function ModelDialog({
    open,
    manage,
    onClose,
    onManage,
    state,
}: {
    open: boolean;
    manage: boolean;
    onClose: () => void;
    onManage: () => void;
    state: ReturnType<typeof useDeskModels>;
}): React.JSX.Element {
    const isLoading = !!state.loading || state.models?.status === "loading";
    const [query, setQuery] = useState("");
    const items =
        state.models?.items.filter((item) =>
            item.display_name.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
        ) ?? [];
    return (
        <Modal
            open={open}
            title={isLoading ? "모델을 불러오는 중" : manage ? "내 로컬 모델" : "로컬 모델 변경"}
            onRequestClose={onClose}
        >
            <div className="desk-model-dialog desk-dialog-stack">
                <p className="muted-copy">이 기기에 설치된 모델 중에서 선택하세요.</p>
                <div className="desk-search-input">
                    <DeskIcon name="5_959-imgIconSearch" />
                    <InputField
                        id="model-search"
                        label="모델 검색"
                        value={query}
                        onChange={(event) => setQuery(event.currentTarget.value)}
                        placeholder="모델 이름 검색"
                    />
                </div>
                {isLoading ? (
                    <div role="status" className="desk-model-loading">
                        <progress />
                        <p>
                            {state.models?.items.find((item) => item.model_id === state.loading)?.display_name ??
                                state.loading}{" "}
                            불러오는 중…
                        </p>
                        <p className="muted-copy">모델 준비가 끝나면 다음 질문에 사용됩니다.</p>
                    </div>
                ) : null}
                {items.map((item) => (
                    <button
                        className={`desk-model-row ${state.models?.active_model_id === item.model_id ? "selected" : ""}`}
                        key={item.model_id}
                        disabled={!item.available || isLoading}
                        onClick={() => void state.select(item.model_id)}
                    >
                        <DeskIcon
                            name={
                                state.models?.active_model_id === item.model_id
                                    ? "5_959-imgIconChip"
                                    : "5_959-imgIconChip1"
                            }
                        />
                        <span>
                            <strong>{item.display_name}</strong>
                            <small>
                                {item.runtime === "llama-cpp" ? "GGUF" : "MLX"} · 컨텍스트{" "}
                                {item.context_limit_tokens.toLocaleString()} 토큰
                            </small>
                            {item.reason ? <small>{item.reason}</small> : null}
                        </span>
                        <em>
                            {state.models?.active_model_id === item.model_id
                                ? "사용 중"
                                : item.available
                                  ? "불러오기"
                                  : "사용 불가"}
                        </em>
                    </button>
                ))}
                {!items.length ? <p>표시할 로컬 모델이 없습니다.</p> : null}
                {state.error || state.models?.error ? <p role="alert">{state.error ?? state.models?.error}</p> : null}
                {state.notice ? (
                    <p className="desk-success" role="status">
                        {state.notice}
                    </p>
                ) : null}
                <div className="desk-model-footer">
                    <p className="muted-copy">모델을 바꿔도 대화 기록은 유지됩니다.</p>
                    <Button variant="quiet" onClick={manage ? () => void state.refresh() : onManage}>
                        {manage ? "목록 새로고침" : "내 모델 관리"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}
