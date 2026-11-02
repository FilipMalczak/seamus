import { useEffect, useState } from "react";
import { AlertTriangle, Check, Code, FolderPlus, List, Save, Trash2, X } from "lucide-react";
import type { SystemSettings } from "../api/types";

interface SettingsModalProps {
  isOpen: boolean;
  initialSettings: SystemSettings;
  onClose: () => void;
  onSave: (updatedSettings: SystemSettings) => Promise<void>;
}

export function SettingsModal({
  isOpen,
  initialSettings,
  onClose,
  onSave,
}: SettingsModalProps) {
  const [skillDirectories, setSkillDirectories] = useState<string[]>([]);
  const [newDirectory, setNewDirectory] = useState<string>("");
  const [rawJson, setRawJson] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"paths" | "json">("paths");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      const dirs = initialSettings.skill_directories || [];
      setSkillDirectories([...dirs]);
      setRawJson(JSON.stringify(initialSettings, null, 2));
      setNewDirectory("");
      setError(null);
      setSuccess(false);
      setActiveTab("paths");
    }
  }, [isOpen, initialSettings]);

  if (!isOpen) return null;

  const handleAddDirectory = () => {
    const trimmed = newDirectory.trim();
    if (!trimmed) return;
    if (skillDirectories.includes(trimmed)) {
      setError(`Directory "${trimmed}" is already added.`);
      return;
    }
    const updated = [...skillDirectories, trimmed];
    setSkillDirectories(updated);
    setNewDirectory("");
    setError(null);
    setRawJson(JSON.stringify({ skill_directories: updated }, null, 2));
  };

  const handleRemoveDirectory = (index: number) => {
    const updated = skillDirectories.filter((_, i) => i !== index);
    setSkillDirectories(updated);
    setError(null);
    setRawJson(JSON.stringify({ skill_directories: updated }, null, 2));
  };

  const handleSwitchTab = (tab: "paths" | "json") => {
    if (tab === "json") {
      setRawJson(JSON.stringify({ skill_directories: skillDirectories }, null, 2));
    } else {
      try {
        const parsed = JSON.parse(rawJson);
        if (parsed && Array.isArray(parsed.skill_directories)) {
          setSkillDirectories(parsed.skill_directories.map(String));
          setError(null);
        } else {
          setError("JSON must contain a 'skill_directories' array.");
          return;
        }
      } catch (err: any) {
        setError(`Cannot switch view: ${err.message}`);
        return;
      }
    }
    setActiveTab(tab);
  };

  const handleFormatJson = () => {
    try {
      const parsed = JSON.parse(rawJson);
      setRawJson(JSON.stringify(parsed, null, 2));
      setError(null);
    } catch (err: any) {
      setError(`Cannot format: ${err.message}`);
    }
  };

  const handleSave = async () => {
    setError(null);
    let finalDirs: string[] = [];

    if (activeTab === "json") {
      try {
        const parsed = JSON.parse(rawJson);
        if (!parsed || !Array.isArray(parsed.skill_directories)) {
          setError("Configuration must contain a 'skill_directories' array.");
          return;
        }
        finalDirs = parsed.skill_directories.map(String);
      } catch (err: any) {
        setError(`Invalid JSON syntax: ${err.message}`);
        return;
      }
    } else {
      finalDirs = [...skillDirectories];
    }

    setSaving(true);
    try {
      await onSave({ skill_directories: finalDirs });
      setSuccess(true);
      setTimeout(() => {
        onClose();
      }, 600);
    } catch (err: any) {
      setError(`Failed to save settings: ${err.message || String(err)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <span className="font-semibold text-zinc-100">System Settings</span>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {/* Prominent Warning Banner */}
          <div
            style={{
              background: "rgba(245, 158, 11, 0.12)",
              border: "1px solid rgba(245, 158, 11, 0.35)",
              color: "#fbbf24",
              padding: "8px 12px",
              borderRadius: "6px",
              fontSize: "0.8rem",
              lineHeight: 1.4,
              display: "flex",
              gap: "8px",
              alignItems: "flex-start",
            }}
          >
            <AlertTriangle size={18} className="shrink-0 mt-0.5 text-amber-400" />
            <div>
              <strong>System-level skills are DISRECOMMENDED</strong> and subject to removal.
              They bypass workspace isolation and Git-tracked provenance. Prefer agent-level skills in{" "}
              <code>&lt;workspace&gt;/data/.skills/</code>.
            </div>
          </div>

          {/* View Mode Toggle */}
          <div style={{ display: "flex", gap: "6px", marginBottom: "4px" }}>
            <button
              type="button"
              className={`btn-secondary ${activeTab === "paths" ? "active" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "4px",
                padding: "4px 10px",
                fontSize: "0.8rem",
                borderRadius: "4px",
                border: "1px solid var(--border-color)",
                background: activeTab === "paths" ? "var(--bg-tertiary)" : "transparent",
                color: activeTab === "paths" ? "#38bdf8" : "var(--text-secondary)",
                cursor: "pointer",
              }}
              onClick={() => handleSwitchTab("paths")}
            >
              <List size={14} />
              <span>Skill Directories</span>
            </button>
            <button
              type="button"
              className={`btn-secondary ${activeTab === "json" ? "active" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "4px",
                padding: "4px 10px",
                fontSize: "0.8rem",
                borderRadius: "4px",
                border: "1px solid var(--border-color)",
                background: activeTab === "json" ? "var(--bg-tertiary)" : "transparent",
                color: activeTab === "json" ? "#38bdf8" : "var(--text-secondary)",
                cursor: "pointer",
              }}
              onClick={() => handleSwitchTab("json")}
            >
              <Code size={14} />
              <span>Raw JSON</span>
            </button>
          </div>

          {activeTab === "paths" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <div style={{ display: "flex", gap: "6px" }}>
                <input
                  type="text"
                  placeholder="Host path (e.g. ~/.seamus/skills or ~/.skills)"
                  value={newDirectory}
                  onChange={(e) => setNewDirectory(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddDirectory();
                    }
                  }}
                  style={{
                    flex: 1,
                    background: "#090d16",
                    border: "1px solid var(--border-color)",
                    borderRadius: "5px",
                    padding: "6px 10px",
                    color: "var(--text-primary)",
                    fontSize: "0.85rem",
                    outline: "none",
                  }}
                />
                <button
                  type="button"
                  onClick={handleAddDirectory}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    background: "#0284c7",
                    border: "none",
                    color: "#fff",
                    borderRadius: "5px",
                    padding: "6px 12px",
                    fontSize: "0.8rem",
                    cursor: "pointer",
                  }}
                >
                  <FolderPlus size={14} />
                  <span>Add</span>
                </button>
              </div>

              <div
                style={{
                  maxHeight: "220px",
                  overflowY: "auto",
                  border: "1px solid var(--border-color)",
                  borderRadius: "6px",
                  background: "#090d16",
                }}
              >
                {skillDirectories.length === 0 ? (
                  <div
                    style={{
                      padding: "16px",
                      textAlign: "center",
                      color: "var(--text-secondary)",
                      fontSize: "0.82rem",
                    }}
                  >
                    No system skill directories configured.
                  </div>
                ) : (
                  skillDirectories.map((dir, idx) => (
                    <div
                      key={dir + idx}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "8px 12px",
                        borderBottom:
                          idx < skillDirectories.length - 1
                            ? "1px solid rgba(255, 255, 255, 0.05)"
                            : "none",
                        fontSize: "0.82rem",
                        fontFamily: "var(--font-mono)",
                        color: "#bae6fd",
                      }}
                    >
                      <span style={{ wordBreak: "break-all" }}>{dir}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveDirectory(idx)}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#f87171",
                          cursor: "pointer",
                          padding: "2px",
                          display: "flex",
                          alignItems: "center",
                        }}
                        title="Remove directory"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : (
            <div className="editor-wrapper">
              <textarea
                className="json-textarea"
                rows={10}
                value={rawJson}
                onChange={(e) => {
                  setRawJson(e.target.value);
                  setError(null);
                }}
                spellCheck={false}
              />
            </div>
          )}

          {error && <div className="alert-error">{error}</div>}
          {success && (
            <div className="alert-success">
              <Check size={14} /> Settings saved successfully!
            </div>
          )}
        </div>

        <div className="modal-footer">
          {activeTab === "json" ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleFormatJson}
              title="Prettify JSON syntax"
            >
              <Code size={14} />
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
              <Save size={14} />
              <span>{saving ? "Saving..." : "Save Settings"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

