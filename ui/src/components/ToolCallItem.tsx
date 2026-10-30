import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import type { ToolCallRecord } from "../api/types";

export function ToolCallItem({ toolCall }: { toolCall: ToolCallRecord }) {
  const [isOpen, setIsOpen] = useState<boolean>(true);

  const hasArgs = toolCall.args && Object.keys(toolCall.args).length > 0;
  const hasResult = toolCall.result !== undefined;

  return (
    <div className="tool-card">
      <button
        type="button"
        className="tool-card-header"
        onClick={() => setIsOpen(!isOpen)}
        title="Toggle tool execution details"
      >
        <div className="tool-card-title">
          <Wrench className="size-3.5 text-amber-400" />
          <span className="tool-name">{toolCall.name}</span>
          {hasResult ? (
            <span className="badge-tool-complete">Completed</span>
          ) : (
            <span className="badge-tool-running">Running...</span>
          )}
        </div>
        {isOpen ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
      </button>

      {isOpen && (
        <div className="tool-card-body">
          {hasArgs && (
            <div className="tool-block">
              <span className="tool-label">Input Arguments:</span>
              <pre className="code-block">{JSON.stringify(toolCall.args, null, 2)}</pre>
            </div>
          )}
          {hasResult && (
            <div className="tool-block">
              <span className="tool-label">Result Output:</span>
              <pre className="code-block">
                {typeof toolCall.result === "string"
                  ? toolCall.result
                  : JSON.stringify(toolCall.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

