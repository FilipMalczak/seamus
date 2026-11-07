import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { A2uiSurface, MarkdownContext } from "@a2ui/react/v0_9";
import { MessageProcessor } from "@a2ui/web_core/v0_9";
import { basicCatalog, setMarkdownRenderer } from "@a2ui/web_core/v0_9/basic_catalog";
import { injectStyles } from "@a2ui/react/styles";
import MarkdownIt from "markdown-it";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { ArtifactInfo } from "../api/types";

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

const defaultMarkdownRenderer = async (text: string) => md.render(text);
setMarkdownRenderer(defaultMarkdownRenderer);

interface ActionPayload {
  name: string;
  surfaceId: string;
  sourceComponentId: string;
  timestamp: string;
  context: Record<string, unknown>;
}

interface CommentRecord {
  id: string;
  location: string; // LN:M format
  selectedText: string;
  comment: string;
  timestamp: string;
}

interface PendingCommentState {
  location: string;
  selectedText: string;
  comment: string;
  top: number;
  left: number;
}

interface A2UIArtifactRendererProps {
  artifact: ArtifactInfo;
  onSubmit?: (data: Record<string, unknown>) => Promise<void> | void;
  onClickButton?: (buttonId: string, context: Record<string, unknown>) => Promise<void> | void;
  isSubmitting?: boolean;
  readOnly?: boolean;
}

/**
 * Normalizes components into standard A2UI basicCatalog specifications.
 * Seamlessly adapts legacy or custom shapes (like ChoiceSet -> ChoicePicker, Text variant 'bold' -> Markdown body).
 */
function normalizeComponents(components: Array<Record<string, any>>): Array<Record<string, any>> {
  return components.map((comp) => {
    if (!comp || typeof comp !== "object") return comp;

    if (comp.component === "Text") {
      let variant = comp.variant;
      let text = comp.text;
      if (variant === "bold") {
        variant = "body";
        if (typeof text === "string" && !text.startsWith("**")) {
          text = `**${text}**`;
        }
      } else if (!["h1", "h2", "h3", "h4", "h5", "caption", "body"].includes(variant)) {
        variant = "body";
      }
      return { ...comp, variant, text };
    }

    if (comp.component === "ChoiceSet" || comp.component === "ChoicePicker") {
      const isMulti = Boolean(comp.isMultiSelect || comp.variant === "multipleSelection");
      const options = (comp.choices || comp.options || []).map((opt: any) => ({
        label: opt.label || opt.text || opt.value || opt.id || "",
        value: String(opt.value || opt.id || ""),
      }));
      let val = comp.value;
      if (val && typeof val === "object" && "path" in val) {
        // Data model pointer: preserve { path: "..." }
      } else if (Array.isArray(val)) {
        val = val.map(String);
      } else if (val !== undefined && val !== null && val !== "") {
        val = [String(val)];
      } else {
        val = [];
      }
      return {
        id: comp.id,
        component: "ChoicePicker",
        variant: isMulti ? "multipleSelection" : "mutuallyExclusive",
        options,
        value: val,
      };
    }

    if (comp.component === "TextInput" || comp.component === "TextField") {
      let val = comp.value;
      if (val && typeof val === "object" && "path" in val) {
        // Data model pointer: preserve { path: "..." }
      } else if (val === undefined || val === null) {
        val = "";
      }
      return {
        id: comp.id,
        component: "TextField",
        label: comp.label || comp.placeholder || "",
        value: val,
      };
    }

    if (comp.component === "Button") {
      let variant = comp.variant;
      if (variant && !["default", "primary", "borderless"].includes(variant)) {
        variant = "default";
      }
      const action = comp.action || {
        event: {
          name: comp.id || "button_click",
          context: {},
        },
      };
      return {
        ...comp,
        action,
        ...(variant ? { variant } : {}),
      };
    }

    return comp;
  });
}

export function A2UIArtifactRenderer({
  artifact,
  onSubmit,
  onClickButton,
  isSubmitting = false,
  readOnly = false,
}: A2UIArtifactRendererProps) {
  const isClosed = artifact.is_closed || readOnly;
  const isEmbedded = artifact.manifest?.exposition === "embedded";
  const isCommentable = Boolean(artifact.manifest?.commentable) && !isClosed;

  const [expanded, setExpanded] = useState<boolean>(!artifact.is_closed || readOnly);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Inline comments state
  const [comments, setComments] = useState<CommentRecord[]>([]);
  const [pendingComment, setPendingComment] = useState<PendingCommentState | null>(null);

  const surfaceContainerRef = useRef<HTMLDivElement>(null);
  const contentContainerRef = useRef<HTMLDivElement>(null);
  const commentTextareaRef = useRef<HTMLTextAreaElement>(null);
  const surfaceId = useMemo(
    () => artifact.uuid || artifact.name || "artifact-surface",
    [artifact.uuid, artifact.name]
  );

  const [surface, setSurface] = useState<any>(null);

  // Auto-focus comment input when opened
  useEffect(() => {
    if (pendingComment) {
      const timer = setTimeout(() => {
        commentTextareaRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [pendingComment?.location]);

  // Text selection handler for inline commenting
  const handleMouseUp = useCallback(() => {
    if (!isCommentable) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;

    const selectedText = sel.toString().trim();
    if (selectedText.length < 2) return;

    const range = sel.getRangeAt(0);
    const container = surfaceContainerRef.current;
    if (!container || !container.contains(range.commonAncestorContainer)) return;

    const contentEl = contentContainerRef.current;
    if (!contentEl) return;

    const startNode = range.startContainer;
    const parentEl = startNode.parentElement;
    const lineIndex = parentEl ? Array.from(parentEl.parentElement?.children || []).indexOf(parentEl) + 1 : 1;
    const location = `L${Math.max(1, lineIndex)}:${range.startOffset + 1}`;

    const contentRect = contentEl.getBoundingClientRect();
    const rangeRect = range.getBoundingClientRect();

    const popoverWidth = 360;
    const popoverHeight = 160;

    let top = rangeRect.bottom - contentRect.top + contentEl.scrollTop + 8;
    if (top + popoverHeight > contentEl.scrollHeight && rangeRect.top - contentRect.top - popoverHeight - 8 > 0) {
      top = rangeRect.top - contentRect.top + contentEl.scrollTop - popoverHeight - 8;
    }

    let left = rangeRect.left - contentRect.left + (rangeRect.width / 2) - (popoverWidth / 2);
    left = Math.max(12, Math.min(left, contentRect.width - popoverWidth - 12));

    setPendingComment({
      location,
      selectedText,
      comment: "",
      top: Math.round(top),
      left: Math.round(left),
    });
  }, [isCommentable]);

  const handleAddComment = () => {
    if (!pendingComment || !pendingComment.comment.trim()) return;
    const newRecord: CommentRecord = {
      id: `comm-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      location: pendingComment.location,
      selectedText: pendingComment.selectedText,
      comment: pendingComment.comment.trim(),
      timestamp: new Date().toISOString(),
    };
    setComments((prev) => [...prev, newRecord]);
    setPendingComment(null);
  };

  const handleRemoveComment = (id: string) => {
    setComments((prev) => prev.filter((c) => c.id !== id));
  };

  const procRef = useRef<MessageProcessor | null>(null);
  const callbacksRef = useRef({
    artifact,
    onSubmit,
    onClickButton,
    isSubmitting,
    isClosed,
    isCommentable,
    comments,
  });

  useEffect(() => {
    callbacksRef.current = {
      artifact,
      onSubmit,
      onClickButton,
      isSubmitting,
      isClosed,
      isCommentable,
      comments,
    };
  });

  // Initialize A2UI MessageProcessor surface
  useEffect(() => {
    injectStyles();

    const proc = new MessageProcessor([basicCatalog], (action: ActionPayload) => {
      const {
        artifact: curArtifact,
        onSubmit: curOnSubmit,
        onClickButton: curOnClickButton,
        isSubmitting: curIsSubmitting,
        isClosed: curIsClosed,
        isCommentable: curIsCommentable,
        comments: curComments,
      } = callbacksRef.current;

      if (curIsClosed || curIsSubmitting) return;

      const buttonId = action.sourceComponentId;
      const manifestBtn = (curArtifact.manifest?.buttons || []).find((b) => b.id === buttonId);
      if (!manifestBtn) {
        console.warn(`[A2UI] Button "${buttonId}" clicked but not declared in manifest.`);
        return;
      }

      const clicksLeft = curArtifact.state?.clicksLeft?.[buttonId];
      if (typeof clicksLeft === "number" && clicksLeft <= 0) {
        console.warn(`[A2UI] Button "${buttonId}" has exhausted clicks.`);
        return;
      }

      const evaluatedContext: Record<string, unknown> = { ...(action.context || {}) };
      if (curIsCommentable && (curComments.length > 0 || buttonId === "review-btn")) {
        evaluatedContext.comments = curComments.map((c) => ({
          location: c.location,
          selectedText: c.selectedText,
          comment: c.comment,
        }));
      }

      try {
        curOnClickButton?.(buttonId, evaluatedContext);
        const submitPromise = curOnSubmit?.({
          button_id: buttonId,
          ...evaluatedContext,
        });
        if (buttonId === "review-btn") {
          setComments([]);
        }
        if (submitPromise && typeof (submitPromise as any).catch === "function") {
          (submitPromise as Promise<void>).catch((err: any) => {
            setSubmitError(err?.message || "Failed to process button click.");
          });
        }
      } catch (err: any) {
        setSubmitError(err?.message || "Failed to process button click.");
      }
    });

    procRef.current = proc;

    try {
      const rawComponents = (artifact.body || (artifact.card as any)?.components || []) as Array<
        Record<string, any>
      >;
      const normalized = normalizeComponents(rawComponents);

      proc.processMessages([
        {
          version: "v0.9",
          createSurface: {
            surfaceId,
            catalogId: basicCatalog.id,
          },
        },
        {
          version: "v0.9",
          updateDataModel: {
            surfaceId,
            path: "/",
            value: artifact.state?.dataModel || artifact.data || {},
          },
        },
        {
          version: "v0.9",
          updateComponents: {
            surfaceId,
            components: normalized,
          },
        },
      ]);

      const surf = proc.model.getSurface(surfaceId);
      setSurface(surf);
    } catch (err: any) {
      console.error("[A2UI] MessageProcessor error:", err);
      setSubmitError(err?.message || "Failed to initialize A2UI surface.");
    }

    return () => {
      proc.dispose();
      if (procRef.current === proc) {
        procRef.current = null;
      }
    };
  }, [surfaceId, artifact.uuid, artifact.name]);

  // Synchronize server-side dataModel updates if state changes externally
  const lastStateModelRef = useRef<string>("");
  useEffect(() => {
    const proc = procRef.current;
    if (!proc || !artifact.state?.dataModel) return;
    const modelStr = JSON.stringify(artifact.state.dataModel);
    if (modelStr !== lastStateModelRef.current) {
      lastStateModelRef.current = modelStr;
      try {
        proc.processMessages([
          {
            version: "v0.9",
            updateDataModel: {
              surfaceId,
              path: "/",
              value: artifact.state.dataModel,
            },
          },
        ]);
      } catch (err) {
        console.warn("[A2UI] Failed to update external dataModel:", err);
      }
    }
  }, [surfaceId, artifact.state?.dataModel]);

  const displayTitle =
    artifact.manifest?.name ||
    artifact.title ||
    (artifact.family === "questionnaires"
      ? "Questionnaire"
      : artifact.family === "forms"
        ? "Form"
        : artifact.family === "plans"
          ? "Plan"
          : "Artifact");

  return (
    <div
      className={`artifact-card a2ui-dark ${
        artifact.is_closed ? "artifact-closed" : "artifact-open"
      } ${artifact.is_closed && !expanded ? "artifact-collapsed" : ""}`}
    >
      {/* Header bar */}
      <div className="artifact-card-header">
        <div className="artifact-header-title">
          {artifact.family === "plans" ? (
            <FileText className="size-4 text-emerald-400" />
          ) : (
            <Sparkles className="size-4 text-sky-400" />
          )}
          <span className="font-semibold text-zinc-100">{displayTitle}</span>
          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-sky-400 border border-sky-400/20">
            A2UI
          </span>
          {artifact.is_closed ? (
            <span className="artifact-status-badge closed">
              <CheckCircle2 className="size-3" /> Closed
            </span>
          ) : artifact.manifest?.blocking ? (
            <span className="artifact-status-badge active">
              Action Required
            </span>
          ) : (
            <span className="artifact-status-badge active">
              Interactive
            </span>
          )}
        </div>

        {isEmbedded && (
          <button
            type="button"
            className="artifact-collapse-toggle-btn"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <>
                <span>Hide</span>
                <ChevronUp className="size-3.5" />
              </>
            ) : (
              <>
                <span>View</span>
                <ChevronDown className="size-3.5" />
              </>
            )}
          </button>
        )}
      </div>

      {/* Main body area */}
      {(!isEmbedded || expanded) && (
        <div
          ref={contentContainerRef}
          className={`artifact-card-content ${
            artifact.is_closed ? "artifact-surface-disabled" : ""
          }`}
        >
          {submitError && (
            <div className="artifact-error-notice">
              <AlertCircle className="size-4 text-rose-400" />
              <span>{submitError}</span>
            </div>
          )}

          {/* Floating inline comment popover */}
          {pendingComment && isCommentable && (
            <div
              className="artifact-comment-popover"
              style={{
                top: `${pendingComment.top}px`,
                left: `${pendingComment.left}px`,
              }}
            >
              <div className="artifact-comment-popover-header">
                <span className="artifact-comment-target-quote" title={pendingComment.selectedText}>
                  Comment on &ldquo;{pendingComment.selectedText}&rdquo;
                </span>
                <span className="artifact-comment-loc-badge">{pendingComment.location}</span>
              </div>
              <textarea
                ref={commentTextareaRef}
                value={pendingComment.comment}
                onChange={(e) =>
                  setPendingComment((prev) => (prev ? { ...prev, comment: e.target.value } : null))
                }
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setPendingComment(null);
                  } else if (
                    e.key === "Enter" &&
                    (e.ctrlKey || e.metaKey) &&
                    pendingComment.comment.trim()
                  ) {
                    e.preventDefault();
                    handleAddComment();
                  }
                }}
                placeholder="Type your comment... (Ctrl+Enter to save, Esc to cancel)"
                rows={3}
                className="artifact-comment-textarea"
              />
              <div className="artifact-comment-popover-actions">
                <button
                  type="button"
                  onClick={() => setPendingComment(null)}
                  className="artifact-comment-cancel-btn"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!pendingComment.comment.trim()}
                  onClick={handleAddComment}
                  className="artifact-comment-submit-btn"
                >
                  Add Comment
                </button>
              </div>
            </div>
          )}

          {/* Render surface using @a2ui/react */}
          {surface ? (
            <div
              ref={surfaceContainerRef}
              onMouseUp={handleMouseUp}
              className={`a2ui-surface-host a2ui-dark select-text ${
                isClosed ? "pointer-events-none opacity-80" : ""
              }`}
            >
              <MarkdownContext.Provider value={defaultMarkdownRenderer}>
                <A2uiSurface surface={surface} />
              </MarkdownContext.Provider>
            </div>
          ) : (
            <p className="artifact-loading">Initializing A2UI surface...</p>
          )}

          {isSubmitting && (
            <div className="artifact-submitting-overlay">
              <span>Submitting...</span>
            </div>
          )}

          {/* Review comments list */}
          {isCommentable && comments.length > 0 && (
            <div className="artifact-comments-section">
              <div className="artifact-comments-header">
                <span className="artifact-comments-title">
                  Attached Comments ({comments.length})
                </span>
                <span className="artifact-comments-subtitle">
                  Will be submitted with your next action
                </span>
              </div>
              <div className="artifact-comments-list">
                {comments.map((comm) => (
                  <div key={comm.id} className="artifact-comment-card">
                    <div className="artifact-comment-card-content">
                      <div className="artifact-comment-card-meta">
                        <span className="artifact-comment-card-loc">{comm.location}</span>
                        <span className="artifact-comment-card-quote">
                          &ldquo;{comm.selectedText}&rdquo;
                        </span>
                      </div>
                      <div className="artifact-comment-card-body">{comm.comment}</div>
                    </div>
                    {!isClosed && (
                      <button
                        type="button"
                        onClick={() => handleRemoveComment(comm.id)}
                        className="artifact-comment-remove-btn"
                        title="Remove comment"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
