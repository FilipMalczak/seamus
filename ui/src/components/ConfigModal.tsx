import { useEffect, useState } from "react";
import { Check, Code, Save, Wand2, X } from "lucide-react";
import type { AgentConfig } from "../api/types";

interface ConfigModalProps {
  title: string;
  initialConfig: AgentConfig;
  isOpen: boolean;
  onClose: () => void;
  onSave: (updatedConfig: AgentConfig) => Promise<void>;
}

export function ConfigModal({
  title,
  initialConfig,
  isOpen,
  onClose,
  onSave,
}: ConfigModalProps) {
  const [jsonText, setJsonText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      setJsonText(JSON.stringify(initialConfig, null, 2));
      setError(null);
      setSuccess(false);
    }
  }, [isOpen, initialConfig]);

  if (!isOpen) return null;

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

    if (
      "rules_implementation" in parsed &&
      parsed.rules_implementation !== null &&
      !["none", "deepagents"].includes(parsed.rules_implementation)
    ) {
      setError(
        `Invalid rules_implementation '${parsed.rules_implementation}'. Allowed values: 'none', 'deepagents'.`
      );
      return;
    }

    if (
      "rules_globs" in parsed &&
      parsed.rules_globs !== null &&
      (!Array.isArray(parsed.rules_globs) ||
        parsed.rules_globs.some((g: unknown) => typeof g !== "string"))
    ) {
      setError("Invalid rules_globs: must be an array of glob strings.");
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

  return (
    <div className="modal-backdrop">
      <div className="modal-panel">
        <div className="modal-header">
          <div className="modal-title">
            <Code className="size-5 text-sky-400" />
            <h3>{title}</h3>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} title="Close">
            <X className="size-5" />
          </button>
        </div>

        <div className="modal-body">
          <p className="modal-description">
            Edit the raw JSON configuration below. Fields such as <code>api_key</code> can be set
            to <code>null</code> to clear or delete their values.
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

          {error && <div className="alert-error">{error}</div>}
          {success && (
            <div className="alert-success">
              <Check className="size-4" />
              <span>Configuration saved successfully!</span>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleFormat}
            title="Format and indent JSON"
          >
            <Wand2 className="size-4" />
            <span>Format JSON</span>
          </button>

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

