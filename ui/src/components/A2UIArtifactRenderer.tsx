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
  const [pendingComment, setPendingComment] = useState<{
    location: string;
    selectedText: string;
    comment: string;
  } | null>(null);

  const surfaceContainerRef = useRef<HTMLDivElement>(null);
  const surfaceId = useMemo(
    () => artifact.uuid || artifact.name || "artifact-surface",
    [artifact.uuid, artifact.name]
  );

  const [surface, setSurface] = useState<any>(null);

  // Text selection handler for inline commenting
  const handleMouseUp = useCallback(() => {
    if (!isCommentable) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;

    const selectedText = sel.toString().trim();
    if (selectedText.length < 2) return;

    const range = sel.getRangeAt(0);
    const startNode = range.startContainer;
    const parentEl = startNode.parentElement;
    const lineIndex = parentEl ? Array.from(parentEl.parentElement?.children || []).indexOf(parentEl) + 1 : 1;
    const location = `L${Math.max(1, lineIndex)}:${range.startOffset + 1}`;

    setPendingComment({
      location,
      selectedText,
      comment: "",
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
      if (curIsCommentable && curComments.length > 0) {
        evaluatedContext.comments = curComments.map((c) => ({
          location: c.location,
          selectedText: c.selectedText,
          comment: c.comment,
        }));
      }

      try {
        curOnClickButton?.(buttonId, evaluatedContext);
        curOnSubmit?.({
          button_id: buttonId,
          ...evaluatedContext,
        });
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

          {/* Pending inline comment editor popover */}
          {pendingComment && isCommentable && (
            <div className="p-3 rounded-xl border border-sky-500/40 bg-zinc-950/95 shadow-xl flex flex-col gap-2.5 z-20 mb-3">
              <div className="flex items-center justify-between text-xs text-zinc-400">
                <span className="font-medium text-sky-400">Comment on &quot;{pendingComment.selectedText}&quot;</span>
                <span className="font-mono text-[11px]">{pendingComment.location}</span>
              </div>
              <textarea
                value={pendingComment.comment}
                onChange={(e) =>
                  setPendingComment((prev) => (prev ? { ...prev, comment: e.target.value } : null))
                }
                placeholder="Type your comment or instruction here..."
                rows={2}
                className="w-full px-3 py-2 text-sm bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-500 resize-none"
              />
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setPendingComment(null)}
                  className="px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!pendingComment.comment.trim()}
                  onClick={handleAddComment}
                  className="px-3 py-1 text-xs bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-md font-medium"
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
            <div className="flex flex-col gap-2 pt-3 border-t border-zinc-800">
              <span className="text-xs font-semibold text-zinc-400">Comments for Agent ({comments.length}):</span>
              {comments.map((comm) => (
                <div
                  key={comm.id}
                  className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/80 flex items-start justify-between gap-3 text-xs"
                >
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] font-mono text-sky-400">
                      {comm.location}: &quot;{comm.selectedText}&quot;
                    </span>
                    <span className="text-zinc-200">{comm.comment}</span>
                  </div>
                  {!isClosed && (
                    <button
                      type="button"
                      onClick={() => handleRemoveComment(comm.id)}
                      className="text-zinc-500 hover:text-rose-400 transition-colors p-1"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
