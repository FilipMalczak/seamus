import { useEffect, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  Check,
  Code,
  Copy,
  Eye,
  EyeOff,
  FolderPlus,
  KeyRound,
  List,
  Lock,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import {
  createOrUpdateVaultSecret,
  getVaultToken,
  listVaultSecrets,
} from "../api/client";
import type { SystemSettings, VaultSecretItem } from "../api/types";

interface SettingsModalProps {
  isOpen: boolean;
  initialSettings: SystemSettings;
  onClose: () => void;
  onSave: (updatedSettings: SystemSettings) => Promise<void>;
}

interface KeyValuePair {
  key: string;
  value: string;
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
  const [activeTab, setActiveTab] = useState<"paths" | "secrets" | "json">("paths");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  // Secrets tab state
  const [secrets, setSecrets] = useState<VaultSecretItem[]>([]);
  const [secretsLoading, setSecretsLoading] = useState<boolean>(false);
  const [secretsError, setSecretsError] = useState<string | null>(null);
  const [secretsSuccess, setSecretsSuccess] = useState<string | null>(null);
  const [copiedExpr, setCopiedExpr] = useState<string | null>(null);
  const [newSecretPath, setNewSecretPath] = useState<string>("");
  const [secretFields, setSecretFields] = useState<KeyValuePair[]>([
    { key: "value", value: "" },
  ]);
  const [secretSaving, setSecretSaving] = useState<boolean>(false);

  // OpenBao login token state
  const [vaultToken, setVaultToken] = useState<string | null>(null);
  const [tokenRevealed, setTokenRevealed] = useState<boolean>(false);
  const [tokenLoading, setTokenLoading] = useState<boolean>(false);
  const [tokenCopied, setTokenCopied] = useState<boolean>(false);

  const loadSecrets = async () => {
    setSecretsLoading(true);
    setSecretsError(null);
    try {
      const res = await listVaultSecrets();
      setSecrets(res.secrets || []);
    } catch (err: any) {
      setSecretsError(err.message || "Failed to load secrets from OpenBao");
    } finally {
      setSecretsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      const dirs = initialSettings.skill_directories || [];
      setSkillDirectories([...dirs]);
      setRawJson(JSON.stringify(initialSettings, null, 2));
      setNewDirectory("");
      setError(null);
      setSuccess(false);
      setActiveTab("paths");
      setSecretsError(null);
      setSecretsSuccess(null);
      setVaultToken(null);
      setTokenRevealed(false);
      setTokenCopied(false);
    }
  }, [isOpen, initialSettings]);

  useEffect(() => {
    if (isOpen && activeTab === "secrets") {
      void loadSecrets();
    }
  }, [isOpen, activeTab]);

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

  const handleSwitchTab = (tab: "paths" | "secrets" | "json") => {
    if (activeTab === "json" && tab !== "json") {
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
    if (tab === "json") {
      setRawJson(JSON.stringify({ skill_directories: skillDirectories }, null, 2));
    }
    setError(null);
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

  const handleToggleRevealToken = async () => {
    if (tokenRevealed) {
      setTokenRevealed(false);
      return;
    }
    if (vaultToken !== null) {
      setTokenRevealed(true);
      return;
    }
    setTokenLoading(true);
    setSecretsError(null);
    try {
      const res = await getVaultToken();
      setVaultToken(res.token || "");
      setTokenRevealed(true);
    } catch (err: any) {
      setSecretsError(err.message || "Failed to retrieve OpenBao login token");
    } finally {
      setTokenLoading(false);
    }
  };

  const handleCopyToken = async () => {
    try {
      let tokenToCopy = vaultToken;
      if (tokenToCopy === null) {
        const res = await getVaultToken();
        tokenToCopy = res.token || "";
        setVaultToken(tokenToCopy);
      }
      if (tokenToCopy) {
        await navigator.clipboard.writeText(tokenToCopy);
        setTokenCopied(true);
        setTimeout(() => setTokenCopied(false), 2000);
      }
    } catch (err: any) {
      setSecretsError(err.message || "Failed to copy OpenBao token");
    }
  };

  const handleAddSecretField = () => {
    setSecretFields([...secretFields, { key: "", value: "" }]);
  };

  const handleRemoveSecretField = (index: number) => {
    if (secretFields.length <= 1) return;
    setSecretFields(secretFields.filter((_, i) => i !== index));
  };

  const handleSecretFieldChange = (
    index: number,
    param: "key" | "value",
    val: string
  ) => {
    const updated = [...secretFields];
    updated[index][param] = val;
    setSecretFields(updated);
  };

  const handleSaveSecret = async (e: FormEvent) => {
    e.preventDefault();
    const cleanPath = newSecretPath.trim().replace(/^\/+/, "");
    if (!cleanPath) {
      setSecretsError("Secret path cannot be empty.");
      return;
    }

    const data: Record<string, string> = {};
    for (const f of secretFields) {
      const k = f.key.trim();
      if (!k) {
        setSecretsError("Field key cannot be empty.");
        return;
      }
      data[k] = f.value;
    }

    setSecretSaving(true);
    setSecretsError(null);
    setSecretsSuccess(null);
    try {
      await createOrUpdateVaultSecret(cleanPath, data);
      setSecretsSuccess(`Secret at '/${cleanPath}' saved.`);
      setNewSecretPath("");
      setSecretFields([{ key: "value", value: "" }]);
      await loadSecrets();
    } catch (err: any) {
      setSecretsError(err.message || "Failed to save secret to OpenBao");
    } finally {
      setSecretSaving(false);
    }
  };

  const copySecretExpr = (expr: string) => {
    void navigator.clipboard.writeText(expr);
    setCopiedExpr(expr);
    setTimeout(() => setCopiedExpr(null), 2000);
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
          {/* View Mode Toggle */}
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
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
              className={`btn-secondary ${activeTab === "secrets" ? "active" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "4px",
                padding: "4px 10px",
                fontSize: "0.8rem",
                borderRadius: "4px",
                border: "1px solid var(--border-color)",
                background: activeTab === "secrets" ? "var(--bg-tertiary)" : "transparent",
                color: activeTab === "secrets" ? "#38bdf8" : "var(--text-secondary)",
                cursor: "pointer",
              }}
              onClick={() => handleSwitchTab("secrets")}
            >
              <Lock size={14} />
              <span>Secrets</span>
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

          {activeTab === "paths" && (
            <>
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
                  marginBottom: "8px",
                }}
              >
                <AlertTriangle size={18} className="shrink-0 mt-0.5 text-amber-400" />
                <div>
                  <strong>System-level skills are DISRECOMMENDED</strong> and subject to removal.
                  They bypass workspace isolation and Git-tracked provenance. Prefer agent-level skills in{" "}
                  <code>&lt;workspace&gt;/data/.skills/</code>.
                </div>
              </div>

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
            </>
          )}

          {activeTab === "secrets" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {/* OpenBao Login Token Section */}
              <div
                style={{
                  border: "1px solid var(--border-color)",
                  borderRadius: "6px",
                  padding: "10px 12px",
                  background: "#090d16",
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <KeyRound size={14} className="text-amber-400" />
                    <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>
                      OpenBao Login Token
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => void handleToggleRevealToken()}
                      disabled={tokenLoading}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        padding: "3px 8px",
                        fontSize: "0.75rem",
                      }}
                    >
                      {tokenRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                      <span>{tokenRevealed ? "Hide" : "Reveal Token"}</span>
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => void handleCopyToken()}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                        padding: "3px 8px",
                        fontSize: "0.75rem",
                      }}
                    >
                      {tokenCopied ? <Check size={13} /> : <Copy size={13} />}
                      <span>{tokenCopied ? "Copied" : "Copy Token"}</span>
                    </button>
                  </div>
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.78rem",
                    color: tokenRevealed ? "#fde68a" : "var(--text-secondary)",
                    background: "rgba(255, 255, 255, 0.03)",
                    padding: "5px 8px",
                    borderRadius: "4px",
                    wordBreak: "break-all",
                  }}
                >
                  {tokenLoading
                    ? "Loading token..."
                    : tokenRevealed
                      ? vaultToken || "(No token configured)"
                      : "••••••••••••••••••••••••••••"}
                </div>
              </div>

              {/* Existing Secrets List */}
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <span
                    style={{
                      fontSize: "0.78rem",
                      fontWeight: 600,
                      color: "var(--text-secondary)",
                      textTransform: "uppercase",
                    }}
                  >
                    Configured Secrets ({secrets.length})
                  </span>
                  <button
                    type="button"
                    onClick={() => void loadSecrets()}
                    disabled={secretsLoading}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "var(--text-secondary)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      fontSize: "0.75rem",
                    }}
                  >
                    <RefreshCw size={12} className={secretsLoading ? "animate-spin" : ""} />
                    <span>Refresh</span>
                  </button>
                </div>

                <div
                  style={{
                    maxHeight: "160px",
                    overflowY: "auto",
                    border: "1px solid var(--border-color)",
                    borderRadius: "6px",
                    background: "#090d16",
                  }}
                >
                  {secretsLoading && secrets.length === 0 ? (
                    <div
                      style={{
                        padding: "14px",
                        textAlign: "center",
                        color: "var(--text-secondary)",
                        fontSize: "0.8rem",
                      }}
                    >
                      Loading secrets...
                    </div>
                  ) : secrets.length === 0 ? (
                    <div
                      style={{
                        padding: "14px",
                        textAlign: "center",
                        color: "var(--text-secondary)",
                        fontSize: "0.8rem",
                      }}
                    >
                      No secrets stored in OpenBao yet.
                    </div>
                  ) : (
                    secrets.map((sec, idx) => (
                      <div
                        key={sec.path}
                        style={{
                          padding: "8px 10px",
                          borderBottom:
                            idx < secrets.length - 1
                              ? "1px solid rgba(255, 255, 255, 0.05)"
                              : "none",
                          display: "flex",
                          flexDirection: "column",
                          gap: "4px",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.82rem",
                              color: "#bae6fd",
                            }}
                          >
                            /{sec.path}
                          </span>
                          {sec.version !== undefined && sec.version !== null && (
                            <span
                              style={{
                                fontSize: "0.7rem",
                                padding: "1px 6px",
                                borderRadius: "4px",
                                background: "rgba(56, 189, 248, 0.15)",
                                color: "#38bdf8",
                                fontFamily: "var(--font-mono)",
                              }}
                            >
                              v{sec.version}
                            </span>
                          )}
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                          {sec.keys.map((k) => {
                            const expr =
                              k === "value"
                                ? `\${secret('/${sec.path}')}`
                                : `\${secret(path='/${sec.path}', field='${k}')}`;
                            const isCopied = copiedExpr === expr;
                            return (
                              <button
                                key={k}
                                type="button"
                                onClick={() => copySecretExpr(expr)}
                                title={`Click to copy ${expr}`}
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "4px",
                                  padding: "2px 6px",
                                  fontSize: "0.72rem",
                                  fontFamily: "var(--font-mono)",
                                  borderRadius: "4px",
                                  border: "1px solid var(--border-color)",
                                  background: "rgba(255, 255, 255, 0.04)",
                                  color: isCopied ? "#34d399" : "var(--text-primary)",
                                  cursor: "pointer",
                                }}
                              >
                                <span>{k}</span>
                                {isCopied ? <Check size={10} /> : <Copy size={10} />}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Add / Update Secret Form */}
              <form
                onSubmit={(e) => void handleSaveSecret(e)}
                style={{
                  border: "1px solid var(--border-color)",
                  borderRadius: "6px",
                  padding: "10px 12px",
                  background: "#090d16",
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                }}
              >
                <span
                  style={{
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    textTransform: "uppercase",
                  }}
                >
                  Add or Update Secret
                </span>
                <input
                  type="text"
                  placeholder="Secret path (e.g. /api-key/inference/openrouter)"
                  value={newSecretPath}
                  onChange={(e) => setNewSecretPath(e.target.value)}
                  style={{
                    background: "var(--bg-primary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "5px",
                    padding: "5px 8px",
                    color: "var(--text-primary)",
                    fontSize: "0.8rem",
                    fontFamily: "var(--font-mono)",
                  }}
                />
                {secretFields.map((f, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                    <input
                      type="text"
                      placeholder="Field (default: value)"
                      value={f.key}
                      onChange={(e) => handleSecretFieldChange(idx, "key", e.target.value)}
                      style={{
                        width: "35%",
                        background: "var(--bg-primary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: "5px",
                        padding: "5px 8px",
                        color: "var(--text-primary)",
                        fontSize: "0.8rem",
                        fontFamily: "var(--font-mono)",
                      }}
                    />
                    <input
                      type={f.value.trim().startsWith("${secret(") ? "text" : "password"}
                      placeholder="Secret value"
                      value={f.value}
                      onChange={(e) => handleSecretFieldChange(idx, "value", e.target.value)}
                      style={{
                        flex: 1,
                        background: "var(--bg-primary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: "5px",
                        padding: "5px 8px",
                        color: "var(--text-primary)",
                        fontSize: "0.8rem",
                        fontFamily: "var(--font-mono)",
                      }}
                    />
                    {secretFields.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemoveSecretField(idx)}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#f87171",
                          cursor: "pointer",
                          padding: "2px",
                        }}
                        title="Remove field"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                ))}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginTop: "2px",
                  }}
                >
                  <button
                    type="button"
                    onClick={handleAddSecretField}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#38bdf8",
                      fontSize: "0.76rem",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                    }}
                  >
                    <Plus size={12} />
                    <span>Add field</span>
                  </button>
                  <button
                    type="submit"
                    disabled={secretSaving}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      background: "#0284c7",
                      border: "none",
                      color: "#fff",
                      borderRadius: "5px",
                      padding: "5px 12px",
                      fontSize: "0.78rem",
                      cursor: "pointer",
                    }}
                  >
                    <Plus size={13} />
                    <span>{secretSaving ? "Saving..." : "Save Secret"}</span>
                  </button>
                </div>
              </form>

              {secretsError && <div className="alert-error">{secretsError}</div>}
              {secretsSuccess && (
                <div className="alert-success">
                  <Check size={14} /> {secretsSuccess}
                </div>
              )}
            </div>
          )}

          {activeTab === "json" && (
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
