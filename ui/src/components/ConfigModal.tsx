import { useEffect, useMemo, useState } from "react";
import { Check, Code, Eye, EyeOff, Save, Sliders, Wand2, X } from "lucide-react";
import type { AgentConfig, SkillsImplementation, TodoImplementation } from "../api/types";

interface ConfigModalProps {
  title: string;
  initialConfig: AgentConfig;
  isOpen: boolean;
  onClose: () => void;
  onSave: (updatedConfig: AgentConfig) => Promise<void>;
}

const MODEL_PRESETS = [
  "openai/gpt-oss-120b",
  "anthropic/claude-sonnet-4",
  "openai/gpt-4.1",
  "openai/gpt-4.1-mini",
  "google/gemini-2.5-pro",
  "google/gemini-2.5-flash",
  "deepseek/deepseek-r1",
];

const BASE_URL_PRESETS = [
  { label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
  { label: "OpenAI", url: "https://api.openai.com/v1" },
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
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      setJsonText(JSON.stringify(initialConfig, null, 2));
      setError(null);
      setSuccess(false);
      setShowApiKey(false);
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
      !["none", "deepagents"].includes(parsed.todo_implementation)
    ) {
      setError(
        `Invalid todo_implementation '${parsed.todo_implementation}'. Allowed values: 'none', 'deepagents'.`
      );
      return;
    }

    if (
      "skills_implementation" in parsed &&
      parsed.skills_implementation !== null &&
      !["none", "deepagents"].includes(parsed.skills_implementation)
    ) {
      setError(
        `Invalid skills_implementation '${parsed.skills_implementation}'. Allowed values: 'none', 'deepagents'.`
      );
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
    parsedDraft?.skills_implementation ?? initialConfig.skills_implementation ?? "deepagents";
  const currentOperationalMode =
    parsedDraft?.mode ?? initialConfig.mode ?? "plan";
  const currentSystemPrompt =
    parsedDraft?.system_prompt !== undefined
      ? parsedDraft.system_prompt
      : initialConfig.system_prompt ?? null;

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

