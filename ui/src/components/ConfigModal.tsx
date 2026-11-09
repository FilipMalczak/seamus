import { useEffect, useMemo, useState } from "react";
import { Check, Code, Eye, EyeOff, Save, Sliders, Wand2, X } from "lucide-react";
import type {
  AgentConfig,
  SkillsImplementation,
  TodoImplementation,
  WebSearchImplementation,
} from "../api/types";

interface ConfigModalProps {
  title: string;
  initialConfig: AgentConfig;
  isOpen: boolean;
  onClose: () => void;
  onSave: (updatedConfig: AgentConfig) => Promise<void>;
}

const MODEL_PRESETS = [
  "openai/gpt-oss-120b",
  "openai/gpt-oss-20b",
  "anthropic/claude-sonnet-4",
  "openai/gpt-4.1",
  "openai/gpt-4.1-mini",
  "google/gemini-2.5-pro",
  "google/gemini-2.5-flash",
  "deepseek/deepseek-r1",
  "gemma4:e4b",
  "llama3.2:3b",
  "qwen3.8:latest",
];

const DAEMON_MODEL_PRESETS = [
  "openai/gpt-oss-20b",
  "openai/gpt-4.1-mini",
  "google/gemini-2.5-flash",
  "llama3.2:3b",
  "qwen3.8:latest",
];

const BASE_URL_PRESETS = [
  { label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
  { label: "OpenAI", url: "https://api.openai.com/v1" },
  { label: "Ollama", url: "http://localhost:11434/v1" },
  { label: "Ollama (Docker)", url: "http://ollama:11434/v1" },
];

export function ConfigModal({
  title,
  initialConfig,
  isOpen,
  onClose,
  onSave,
}: ConfigModalProps) {
  const [mode, setMode] = useState<"form" | "json">("form");
  const [jsonText, setJsonText] = useState<string>("");
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [showDaemonApiKey, setShowDaemonApiKey] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      setJsonText(JSON.stringify(initialConfig, null, 2));
      setError(null);
      setSuccess(false);
      setShowApiKey(false);
      setShowDaemonApiKey(false);
    }
  }, [isOpen, initialConfig]);

  const parsedDraft = useMemo< Record<string, any> | null>(() => {
    try {
      const obj = JSON.parse(jsonText);
      return obj && typeof obj === "object" ? obj : null;
    } catch {
      return null;
    }
  }, [jsonText]);

  if (!isOpen) return null;

  const updateDraft = (updater: (draft: Record<string, any>) => void) => {
    const base = parsedDraft
      ? JSON.parse(JSON.stringify(parsedDraft))
      : JSON.parse(JSON.stringify(initialConfig));
    if (!base.inference || typeof base.inference !== "object") {
      base.inference = {
        format: "openai",
        base_url: "https://openrouter.ai/api/v1",
        api_key: "${secret('/api-key/inference/openrouter')}",
      };
    }
    updater(base);
    setJsonText(JSON.stringify(base, null, 2));
    setError(null);
  };

  const handleModeSwitch = (targetMode: "form" | "json") => {
    if (targetMode === "form" && !parsedDraft) {
      setError("Fix JSON syntax errors before switching to Form view.");
      return;
    }
    setError(null);
    setMode(targetMode);
  };

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(jsonText);
      setJsonText(JSON.stringify(parsed, null, 2));
      setError(null);
    } catch (err: any) {
      setError(`Cannot format: ${err.message}`);
    }
  };

  const handleSave = async () => {
    setError(null);
    let parsed: any;
    try {
      parsed = JSON.parse(jsonText);
    } catch (err: any) {
      setError(`Invalid JSON syntax: ${err.message}`);
      return;
    }

    if (!parsed || typeof parsed !== "object") {
      setError("Configuration must be a valid JSON object.");
      return;
    }

    if (
      "todo_implementation" in parsed &&
      parsed.todo_implementation !== null &&
      !["none", "deepagents", "seamus"].includes(parsed.todo_implementation)
    ) {
      setError(
        `Invalid todo_implementation '${parsed.todo_implementation}'. Allowed values: 'none', 'deepagents', 'seamus'.`
      );
      return;
    }

    if (
      "skills_implementation" in parsed &&
      parsed.skills_implementation !== null &&
      !["none", "deepagents", "seamus"].includes(parsed.skills_implementation)
    ) {
      setError(
        `Invalid skills_implementation '${parsed.skills_implementation}'. Allowed values: 'none', 'deepagents', 'seamus'.`
      );
      return;
    }

    if (
      "web_search" in parsed &&
      parsed.web_search !== null &&
      !["none", "duckduckgo"].includes(parsed.web_search)
    ) {
      setError(
        `Invalid web_search '${parsed.web_search}'. Allowed values: 'none', 'duckduckgo'.`
      );
      return;
    }

    if (
      parsed.daemons?.naming?.enabled &&
      (!parsed.daemons?.naming?.model || !parsed.daemons.naming.model.trim())
    ) {
      setError("Naming daemon model must be specified when naming daemon is enabled.");
      return;
    }

    setSaving(true);
    try {
      await onSave(parsed as AgentConfig);
      setSuccess(true);
      setTimeout(() => {
        onClose();
      }, 700);
    } catch (err: any) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const currentModel = parsedDraft?.model_name ?? initialConfig.model_name ?? "";
  const currentFormat =
    parsedDraft?.inference?.format ?? initialConfig.inference?.format ?? "openai";
  const currentBaseUrl =
    parsedDraft?.inference?.base_url ?? initialConfig.inference?.base_url ?? "";
  const currentApiKey =
    parsedDraft?.inference?.api_key !== undefined
      ? parsedDraft.inference.api_key
      : initialConfig.inference?.api_key ?? null;
  const currentTodoImpl: TodoImplementation =
    parsedDraft?.todo_implementation ?? initialConfig.todo_implementation ?? "deepagents";
  const currentSkillsImpl: SkillsImplementation =
    parsedDraft?.skills_implementation ?? initialConfig.skills_implementation ?? "seamus";
  const currentOperationalMode =
    parsedDraft?.mode ?? initialConfig.mode ?? "plan";
  const currentWebSearch: WebSearchImplementation =
    parsedDraft?.web_search ?? initialConfig.web_search ?? "duckduckgo";
  const currentSystemPrompt =
    parsedDraft?.system_prompt !== undefined
      ? parsedDraft.system_prompt
      : initialConfig.system_prompt ?? null;

  const daemonNaming = parsedDraft?.daemons?.naming ?? initialConfig.daemons?.naming;
  const isNamingEnabled = daemonNaming?.enabled ?? true;
  const namingModel = daemonNaming?.model ?? "openai/gpt-oss-20b";
  const namingProvider = daemonNaming?.provider ?? null;
  const hasCustomDaemonProvider = namingProvider !== null && typeof namingProvider === "object";
  const daemonFormat = namingProvider?.format ?? "openai";
  const daemonBaseUrl = namingProvider?.base_url ?? "";
  const daemonApiKey = namingProvider?.api_key ?? null;

  const isPresetModel = MODEL_PRESETS.includes(currentModel);

  return (
    <div className="modal-backdrop">
      <div className="modal-panel">
        <div className="modal-header">
          <div className="modal-title">
            {mode === "form" ? (
              <Sliders className="size-5 text-sky-400" />
            ) : (
              <Code className="size-5 text-sky-400" />
            )}
            <h3>{title}</h3>
          </div>
          <div className="config-mode-tabs">
            <button
              type="button"
              className={`config-mode-tab ${mode === "form" ? "active" : ""}`}
              onClick={() => handleModeSwitch("form")}
            >
              <Sliders className="size-3.5" />
              <span>Form</span>
            </button>
            <button
              type="button"
              className={`config-mode-tab ${mode === "json" ? "active" : ""}`}
              onClick={() => handleModeSwitch("json")}
            >
              <Code className="size-3.5" />
              <span>Raw JSON</span>
            </button>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} title="Close">
            <X className="size-5" />
          </button>
        </div>

        <div className="modal-body">
          {mode === "form" && parsedDraft ? (
            <div className="config-form">
              <div className="config-form-row">
                <div className="config-field">
                  <label className="config-label">Model Preset / Catalog</label>
                  <select
                    className="config-select"
                    value={isPresetModel ? currentModel : "__custom__"}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val !== "__custom__") {
                        updateDraft((d) => {
                          d.model_name = val;
                        });
                      }
                    }}
                  >
                    {MODEL_PRESETS.map((preset) => (
                      <option key={preset} value={preset}>
                        {preset}
                      </option>
                    ))}
                    <option value="__custom__">Custom model identifier...</option>
                  </select>
                </div>

                <div className="config-field">
                  <label className="config-label">Model Identifier</label>
                  <input
                    type="text"
                    className="config-input"
                    value={currentModel}
                    placeholder="e.g. openai/gpt-oss-120b"
                    onChange={(e) =>
                      updateDraft((d) => {
                        d.model_name = e.target.value;
                      })
                    }
                  />
                </div>
              </div>

              <div className="config-form-row">
                <div className="config-field">
                  <label className="config-label">Inference Format</label>
                  <select
                    className="config-select"
                    value={currentFormat}
                    onChange={(e) =>
                      updateDraft((d) => {
                        d.inference.format = e.target.value;
                      })
                    }
                  >
                    <option value="openai">openai (OpenAI-compatible)</option>
                    <option value="ollama">ollama (Local Ollama)</option>
                  </select>
                </div>

                <div className="config-field">
                  <div className="config-label-row">
                    <label className="config-label">Base URL</label>
                    <div className="config-preset-pills">
                      {BASE_URL_PRESETS.map((p) => (
                        <button
                          key={p.label}
                          type="button"
                          className={`config-preset-pill ${
                            currentBaseUrl === p.url ? "active" : ""
                          }`}
                          onClick={() =>
                            updateDraft((d) => {
                              d.inference.base_url = p.url;
                            })
                          }
                        >
                          {p.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <input
                    type="text"
                    className="config-input"
                    value={currentBaseUrl}
                    placeholder="https://openrouter.ai/api/v1"
                    onChange={(e) =>
                      updateDraft((d) => {
                        d.inference.base_url = e.target.value;
                      })
                    }
                  />
                </div>
              </div>

              <div className="config-field">
                <div className="config-label-row">
                  <label className="config-label">
                    API Key{" "}
                    <span className="config-label-subtle">
                      ({currentApiKey === null ? "null / unset" : "configured"})
                    </span>
                  </label>
                  {currentApiKey !== null && (
                    <button
                      type="button"
                      className="config-clear-btn"
                      onClick={() =>
                        updateDraft((d) => {
                          d.inference.api_key = null;
                        })
                      }
                    >
                      Clear (set null)
                    </button>
                  )}
                </div>
                <div className="config-input-with-action">
                  <input
                    type={
                      showApiKey || (currentApiKey ?? "").trim().startsWith("${secret(")
                        ? "text"
                        : "password"
                    }
                    className="config-input"
                    value={currentApiKey ?? ""}
                    placeholder="${secret('/api-key/inference/openrouter')}"
                    onChange={(e) => {
                      const val = e.target.value;
                      updateDraft((d) => {
                        d.inference.api_key = val === "" ? null : val;
                      });
                    }}
                  />
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => setShowApiKey((prev) => !prev)}
                    title={showApiKey ? "Hide API key" : "Show API key"}
                  >
                    {showApiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>

              <div className="config-form-row">
                <div className="config-field">
                  <label className="config-label">Todo Implementation</label>
                  <select
                    className="config-select"
                    value={currentTodoImpl}
                    onChange={(e) =>
                      updateDraft((d) => {
                        d.todo_implementation = e.target.value;
                      })
                    }
                  >
                    <option value="seamus">seamus (Native LM-XML)</option>
                    <option value="deepagents">deepagents (TodoListMiddleware)</option>
                    <option value="none">none (Disabled)</option>
                  </select>
                </div>

                <div className="config-field">
                  <label className="config-label">Skills Implementation</label>
                  <select
                    className="config-select"
                    value={currentSkillsImpl}
                    onChange={(e) =>
                      updateDraft((d) => {
                        d.skills_implementation = e.target.value;
                      })
                    }
                  >
                    <option value="seamus">seamus (Native LM-XML with load/unload)</option>
                    <option value="deepagents">deepagents (SkillsMiddleware)</option>
                    <option value="none">none (Disabled)</option>
                  </select>
                </div>
              </div>

              <div className="config-form-row">
                <div className="config-field">
                  <label className="config-label">Default Operational Mode</label>
                  <select
                    className="config-select"
                    value={currentOperationalMode}
                    onChange={(e) =>
                      updateDraft((d) => {
                        d.mode = e.target.value;
                      })
                    }
                  >
                    <option value="plan">plan (3-phase Discuss &gt; Make &gt; Execute workflow)</option>
                    <option value="chat">chat (Direct conversational/coding mode)</option>
                  </select>
                </div>

                <div className="config-field">
                  <label className="config-label">Web Search</label>
                  <select
                    className="config-select"
                    value={currentWebSearch}
                    onChange={(e) =>
                      updateDraft((d) => {
                        d.web_search = e.target.value;
                      })
                    }
                  >
                    <option value="duckduckgo">duckduckgo (DuckDuckGo Search & Extraction)</option>
                    <option value="none">none (Disabled)</option>
                  </select>
                </div>
              </div>

              <div className="config-section-divider">
                <div className="config-section-title">Background Daemons (Automated Naming)</div>
              </div>

              <div className="config-form-row">
                <div className="config-field">
                  <label className="config-label">Naming Daemon Status</label>
                  <select
                    className="config-select"
                    value={isNamingEnabled ? "enabled" : "disabled"}
                    onChange={(e) => {
                      const enabled = e.target.value === "enabled";
                      updateDraft((d) => {
                        if (!d.daemons) d.daemons = {};
                        if (!d.daemons.naming) d.daemons.naming = {};
                        d.daemons.naming.enabled = enabled;
                        if (enabled && !d.daemons.naming.model) {
                          d.daemons.naming.model = "openai/gpt-oss-20b";
                        }
                      });
                    }}
                  >
                    <option value="enabled">Enabled (Auto-name threads and sessions)</option>
                    <option value="disabled">Disabled</option>
                  </select>
                </div>

                <div className="config-field">
                  <div className="config-label-row">
                    <label className="config-label">Naming Model Identifier</label>
                    <div className="config-preset-pills">
                      {DAEMON_MODEL_PRESETS.map((p) => (
                        <button
                          key={p}
                          type="button"
                          className={`config-preset-pill ${namingModel === p ? "active" : ""}`}
                          onClick={() =>
                            updateDraft((d) => {
                              if (!d.daemons) d.daemons = {};
                              if (!d.daemons.naming) d.daemons.naming = {};
                              d.daemons.naming.model = p;
                            })
                          }
                        >
                          {p.split("/").pop()}
                        </button>
                      ))}
                    </div>
                  </div>
                  <input
                    type="text"
                    className="config-input"
                    value={namingModel}
                    placeholder="e.g. openai/gpt-oss-20b"
                    onChange={(e) =>
                      updateDraft((d) => {
                        if (!d.daemons) d.daemons = {};
                        if (!d.daemons.naming) d.daemons.naming = {};
                        d.daemons.naming.model = e.target.value;
                      })
                    }
                  />
                </div>
              </div>

              <div className="config-field">
                <div className="config-label-row">
                  <label className="config-label">
                    Daemon Inference Provider:{" "}
                    <span className="config-label-subtle">
                      {hasCustomDaemonProvider
                        ? "Custom provider configured"
                        : "Inherits agent-level provider"}
                    </span>
                  </label>
                  {hasCustomDaemonProvider ? (
                    <button
                      type="button"
                      className="config-clear-btn"
                      onClick={() =>
                        updateDraft((d) => {
                          if (d.daemons?.naming) {
                            d.daemons.naming.provider = null;
                          }
                        })
                      }
                    >
                      Reset to Agent Provider
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="config-clear-btn"
                      onClick={() =>
                        updateDraft((d) => {
                          if (!d.daemons) d.daemons = {};
                          if (!d.daemons.naming) d.daemons.naming = {};
                          d.daemons.naming.provider = {
                            format: "openai",
                            base_url: "https://openrouter.ai/api/v1",
                            api_key: "${secret('/api-key/inference/openrouter')}",
                          };
                        })
                      }
                    >
                      + Use Custom Daemon Provider
                    </button>
                  )}
                </div>
                <div className="text-xs text-zinc-400">
                  Automated thread naming triggers on 1st, 3rd, 7th, 15th, ... completed exchange.
                </div>
              </div>

              {hasCustomDaemonProvider && (
                <>
                  <div className="config-form-row">
                    <div className="config-field">
                      <label className="config-label">Daemon Provider Format</label>
                      <select
                        className="config-select"
                        value={daemonFormat}
                        onChange={(e) =>
                          updateDraft((d) => {
                            if (!d.daemons) d.daemons = {};
                            if (!d.daemons.naming) d.daemons.naming = {};
                            if (!d.daemons.naming.provider) d.daemons.naming.provider = {};
                            d.daemons.naming.provider.format = e.target.value;
                          })
                        }
                      >
                        <option value="openai">openai (OpenAI-compatible)</option>
                        <option value="ollama">ollama (Local Ollama)</option>
                      </select>
                    </div>

                    <div className="config-field">
                      <div className="config-label-row">
                        <label className="config-label">Daemon Base URL</label>
                        <div className="config-preset-pills">
                          {BASE_URL_PRESETS.map((p) => (
                            <button
                              key={p.label}
                              type="button"
                              className={`config-preset-pill ${
                                daemonBaseUrl === p.url ? "active" : ""
                              }`}
                              onClick={() =>
                                updateDraft((d) => {
                                  if (!d.daemons) d.daemons = {};
                                  if (!d.daemons.naming) d.daemons.naming = {};
                                  if (!d.daemons.naming.provider) d.daemons.naming.provider = {};
                                  d.daemons.naming.provider.base_url = p.url;
                                })
                              }
                            >
                              {p.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      <input
                        type="text"
                        className="config-input"
                        value={daemonBaseUrl}
                        placeholder="https://openrouter.ai/api/v1"
                        onChange={(e) =>
                          updateDraft((d) => {
                            if (!d.daemons) d.daemons = {};
                            if (!d.daemons.naming) d.daemons.naming = {};
                            if (!d.daemons.naming.provider) d.daemons.naming.provider = {};
                            d.daemons.naming.provider.base_url = e.target.value;
                          })
                        }
                      />
                    </div>
                  </div>

                  <div className="config-field">
                    <div className="config-label-row">
                      <label className="config-label">Daemon API Key</label>
                      {daemonApiKey !== null && (
                        <button
                          type="button"
                          className="config-clear-btn"
                          onClick={() =>
                            updateDraft((d) => {
                              if (d.daemons?.naming?.provider) {
                                d.daemons.naming.provider.api_key = null;
                              }
                            })
                          }
                        >
                          Clear
                        </button>
                      )}
                    </div>
                    <div className="config-input-with-action">
                      <input
                        type={showDaemonApiKey ? "text" : "password"}
                        className="config-input"
                        value={daemonApiKey ?? ""}
                        placeholder="Daemon API key or ${secret('/api-key/...')}"
                        onChange={(e) => {
                          const val = e.target.value;
                          updateDraft((d) => {
                            if (!d.daemons) d.daemons = {};
                            if (!d.daemons.naming) d.daemons.naming = {};
                            if (!d.daemons.naming.provider) d.daemons.naming.provider = {};
                            d.daemons.naming.provider.api_key = val === "" ? null : val;
                          });
                        }}
                      />
                      <button
                        type="button"
                        className="icon-btn"
                        onClick={() => setShowDaemonApiKey((v) => !v)}
                        title={showDaemonApiKey ? "Hide daemon API key" : "Show daemon API key"}
                      >
                        {showDaemonApiKey ? (
                          <EyeOff className="size-4" />
                        ) : (
                          <Eye className="size-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </>
              )}

              <div className="config-field">
                <div className="config-label-row">
                  <label className="config-label">Rules & Context Patterns (rules_patterns)</label>
                  <button
                    type="button"
                    className="config-clear-btn"
                    onClick={() =>
                      updateDraft((d) => {
                        if (!Array.isArray(d.rules_patterns)) {
                          d.rules_patterns = ["AGENTS.md", ".seamus/rules/**"];
                        }
                        d.rules_patterns.push("");
                      })
                    }
                  >
                    + Add Pattern
                  </button>
                </div>
                <div className="text-xs text-zinc-400 mb-2">
                  Glob patterns searched in <code>/workspace</code> and mounted <code>/projects/*</code>, injected into dynamic prompt <code>&lt;discovered_context&gt;</code>.
                </div>
                {Array.isArray(parsedDraft.rules_patterns) && parsedDraft.rules_patterns.length > 0 ? (
                  <div className="space-y-2 mb-2">
                    {parsedDraft.rules_patterns.map((pat: string, idx: number) => (
                      <div key={idx} className="flex items-center gap-2 bg-zinc-900/60 p-2 rounded border border-zinc-800">
                        <input
                          type="text"
                          className="config-input flex-1"
                          placeholder="e.g. AGENTS.md or .seamus/rules/**"
                          value={pat || ""}
                          onChange={(e) =>
                            updateDraft((d) => {
                              d.rules_patterns[idx] = e.target.value;
                            })
                          }
                        />
                        <button
                          type="button"
                          className="icon-btn text-rose-400 hover:text-rose-300"
                          title="Remove pattern"
                          onClick={() =>
                            updateDraft((d) => {
                              d.rules_patterns.splice(idx, 1);
                            })
                          }
                        >
                          <X className="size-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-zinc-500 italic mb-2">No rules patterns defined (defaults to AGENTS.md and .seamus/rules/**).</div>
                )}
              </div>

              <div className="config-field">
                <div className="config-label-row">
                  <label className="config-label">Mounted Git Repositories (/projects/)</label>
                  <button
                    type="button"
                    className="config-clear-btn"
                    onClick={() =>
                      updateDraft((d) => {
                        if (!Array.isArray(d.repositories)) {
                          d.repositories = [];
                        }
                        d.repositories.push({
                          url: "",
                          branch: "main",
                          credentials: "",
                        });
                      })
                    }
                  >
                    + Add Repository
                  </button>
                </div>
                <div className="text-xs text-zinc-400 mb-2">
                  External Git repositories mounted under <code>/projects/&lt;name&gt;</code>.
                  Credentials should reference an OpenBao secret like <code>{"${secret('/git/token')}"}</code>.
                </div>
                {Array.isArray(parsedDraft.repositories) && parsedDraft.repositories.length > 0 ? (
                  <div className="space-y-2 mb-2">
                    {parsedDraft.repositories.map((repo: any, idx: number) => (
                      <div key={repo.id || idx} className="flex items-center gap-2 bg-zinc-900/60 p-2 rounded border border-zinc-800">
                        <input
                          type="text"
                          className="config-input flex-1"
                          placeholder="Git URL (e.g. https://github.com/org/repo.git)"
                          value={repo.url || ""}
                          onChange={(e) =>
                            updateDraft((d) => {
                              d.repositories[idx].url = e.target.value;
                            })
                          }
                        />
                        <input
                          type="text"
                          className="config-input w-28"
                          placeholder="Branch"
                          value={repo.branch || "main"}
                          onChange={(e) =>
                            updateDraft((d) => {
                              d.repositories[idx].branch = e.target.value;
                            })
                          }
                        />
                        <input
                          type="text"
                          className="config-input w-48"
                          placeholder="${secret('/git/token')}"
                          value={repo.credentials || ""}
                          onChange={(e) =>
                            updateDraft((d) => {
                              d.repositories[idx].credentials = e.target.value || null;
                            })
                          }
                        />
                        <button
                          type="button"
                          className="icon-btn text-rose-400 hover:text-rose-300"
                          title="Remove repository"
                          onClick={() =>
                            updateDraft((d) => {
                              d.repositories.splice(idx, 1);
                            })
                          }
                        >
                          <X className="size-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-zinc-500 italic mb-2">No external repositories mounted.</div>
                )}
              </div>

              <div className="config-field">
                <div className="config-label-row">
                  <label className="config-label">Sandbox Container Image</label>
                  {parsedDraft.sandbox_image && (
                    <button
                      type="button"
                      className="config-clear-btn"
                      onClick={() =>
                        updateDraft((d) => {
                          d.sandbox_image = null;
                        })
                      }
                    >
                      Reset to default
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  className="config-input"
                  value={parsedDraft.sandbox_image || ""}
                  placeholder="seamus-sandbox:latest (default)"
                  onChange={(e) => {
                    const val = e.target.value.trim();
                    updateDraft((d) => {
                      d.sandbox_image = val === "" ? null : val;
                    });
                  }}
                />
              </div>

              <div className="config-field">
                <div className="config-label-row">
                  <label className="config-label">Custom System Prompt</label>
                  {currentSystemPrompt !== null && (
                    <button
                      type="button"
                      className="config-clear-btn"
                      onClick={() =>
                        updateDraft((d) => {
                          d.system_prompt = null;
                        })
                      }
                    >
                      Clear (set null)
                    </button>
                  )}
                </div>
                <textarea
                  className="config-textarea"
                  rows={4}
                  value={currentSystemPrompt ?? ""}
                  placeholder="Optional custom instructions injected into <custom_instructions>..."
                  onChange={(e) => {
                    const val = e.target.value;
                    updateDraft((d) => {
                      d.system_prompt = val === "" ? null : val;
                    });
                  }}
                />
              </div>
            </div>
          ) : (
            <>
              <p className="modal-description">
                Edit the raw JSON configuration below. Fields such as <code>api_key</code> can be
                set to <code>null</code> to clear or delete their values.
              </p>

              <div className="editor-wrapper">
                <textarea
                  className="json-textarea"
                  value={jsonText}
                  onChange={(e) => {
                    setJsonText(e.target.value);
                    setError(null);
                  }}
                  spellCheck={false}
                  rows={14}
                />
              </div>
            </>
          )}

          {error && <div className="alert-error">{error}</div>}
          {success && (
            <div className="alert-success">
              <Check className="size-4" />
              <span>Configuration saved successfully!</span>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {mode === "json" ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleFormat}
              title="Format and indent JSON"
            >
              <Wand2 className="size-4" />
              <span>Format JSON</span>
            </button>
          ) : (
            <div />
          )}

          <div className="footer-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSave}
              disabled={saving}
            >
              <Save className="size-4" />
              <span>{saving ? "Saving..." : "Save Configuration"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

