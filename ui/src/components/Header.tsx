import { Bot, Settings, Zap } from "lucide-react";
import type { AgentConfig } from "../api/types";

interface HeaderProps {
  configTemplate: AgentConfig | null;
  onOpenConfigTemplate: () => void;
}

export function Header({ configTemplate, onOpenConfigTemplate }: HeaderProps) {
  const modelName = configTemplate?.model_name || "openai/gpt-oss-120b";
  const baseUrl = configTemplate?.inference.base_url || "OpenRouter";

  return (
    <header className="app-header">
      <div className="header-left">
        <div className="brand-logo">
          <Bot className="size-5 text-sky-400" />
        </div>
        <div>
          <div className="brand-title">
            <h1>Seamus</h1>
            <span className="badge-agent">DeepAgent</span>
          </div>
          <div className="brand-meta">
            <Zap className="size-3 text-amber-400" />
            <span>{modelName}</span>
            <span className="meta-sep">&bull;</span>
            <span title={baseUrl}>{baseUrl.replace("https://", "")}</span>
            <span className="meta-sep">&bull;</span>
            <span>AG-UI SSE</span>
          </div>
        </div>
      </div>

      <div className="header-right">
        <button
          type="button"
          className="btn-header-action"
          onClick={onOpenConfigTemplate}
          title="Edit singleton Config Template"
        >
          <Settings className="size-4" />
          <span>Config Template</span>
        </button>
      </div>
    </header>
  );
}

