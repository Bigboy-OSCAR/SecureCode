import type { ToolCallSummary } from "@securecode/contracts";
import { outputLabel, phaseLabel, toolLabel } from "../model/toolLabels.js";

interface ToolHistoryProps {
    tools: readonly ToolCallSummary[] | null;
    truncated: boolean;
}

export function ToolHistory({ tools, truncated }: ToolHistoryProps): React.JSX.Element {
    return (
        <div className="tool-history">
            <h3>실행 도구 이력</h3>
            {tools === null ? <p>현재 실행의 도구 이력은 실행 후 확인할 수 있습니다.</p> : null}
            {tools?.length === 0 ? <p>이 실행은 도구를 사용하지 않았습니다.</p> : null}
            {tools?.map((tool) => (
                <div className="tool-row" key={tool.tool_call_id} data-testid="tool-row">
                    <strong>
                        {toolLabel(tool.tool_name)} · {phaseLabel(tool.phase)}
                    </strong>
                    <span>{tool.summary}</span>
                    <span>{outputLabel(tool)}</span>
                    {tool.output_pointer ? <span>등록 자료 › 현재 세션의 Runtime Pointer에서 부분 읽기</span> : null}
                </div>
            ))}
            {truncated ? <p>도구 이력 일부만 표시됩니다.</p> : null}
        </div>
    );
}
