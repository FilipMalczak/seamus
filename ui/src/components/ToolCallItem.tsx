import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Globe,
  Loader2,
  Wrench,
  XCircle,
} from "lucide-react";
import type { ToolCallRecord } from "../api/types";

export function ToolCallItem({ toolCall }: { toolCall: ToolCallRecord }) {
  const status = toolCall.status || (toolCall.result !== undefined ? "done" : "pending");
  const isDone = status === "done" || status === "error";

  const [userToggled, setUserToggled] = useState<boolean>(false);
  const [isOpen, setIsOpen] = useState<boolean>(!isDone);

  // Auto-collapse when tool execution completes (unless user manually toggled)
  useEffect(() => {
    if (!userToggled) {
      setIsOpen(!isDone);
    }
  }, [isDone, userToggled]);

  const hasArgs =
    (toolCall.args &&
      (typeof toolCall.args === "string"
        ? toolCall.args.trim().length > 0
        : Object.keys(toolCall.args).length > 0)) ||
    Boolean(toolCall.rawArgs && toolCall.rawArgs.trim().length > 0);
  const hasResult = toolCall.result !== undefined;

  const renderBadge = () => {
    switch (status) {
      case "pending":
        return (
          <span className="badge-tool-pending" title="Tool call arguments preparing">
            <Clock className="size-2.5" />
            <span>Pending</span>
          </span>
        );
      case "wip":
        return (
          <span className="badge-tool-running" title="Tool executing in sandbox/backend">
            <Loader2 className="size-2.5 animate-spin" />
            <span>WIP</span>
          </span>
        );
      case "done":
        return (
          <span className="badge-tool-complete" title="Tool execution completed">
            <CheckCircle2 className="size-2.5" />
            <span>Done</span>
          </span>
        );
      case "error":
        return (
          <span className="badge-tool-error" title="Tool execution encountered an error">
            <XCircle className="size-2.5" />
            <span>Failed</span>
          </span>
        );
      default:
        return (
          <span className="badge-tool-pending">
            <span>{status}</span>
          </span>
        );
    }
  };

  return (
    <div className="tool-card">
      <button
        type="button"
        className="tool-card-header"
        onClick={() => {
          setUserToggled(true);
          setIsOpen((prev) => !prev);
        }}
        title="Toggle tool execution details"
      >
        <div className="tool-card-title">
          {toolCall.name === "web_search" || toolCall.name === "fetch_web_page" ? (
            <Globe className="size-3.5 text-emerald-400" />
          ) : (
            <Wrench className="size-3.5 text-amber-400" />
          )}
          <span className="tool-name">{toolCall.name}</span>
          {renderBadge()}
        </div>
        {isOpen ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
      </button>

      {isOpen && (
        <div className="tool-card-body">
          {hasArgs && (
            <div className="tool-block">
              <span className="tool-label">Input Arguments:</span>
              <pre className="code-block">
                {typeof toolCall.args === "object" && toolCall.args !== null
                  ? JSON.stringify(toolCall.args, null, 2)
                  : toolCall.rawArgs || String(toolCall.args)}
              </pre>
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
