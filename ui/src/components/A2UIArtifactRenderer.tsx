import React, { useState, useMemo, useCallback } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  Lock,
  MessageSquare,
  Sparkles,
  X,
} from "lucide-react";
import type { ArtifactInfo } from "../api/types";
import { MarkdownRenderer } from "./MarkdownRenderer";

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

export function A2UIArtifactRenderer({
  artifact,
  onSubmit,
  onClickButton,
  isSubmitting = false,
  readOnly = false,
}: A2UIArtifactRendererProps) {
  const isClosed = artifact.is_closed || readOnly;
  const isEmbedded = artifact.manifest.exposition === "embedded";
  const isCommentable = Boolean(artifact.manifest.commentable) && !isClosed;

  const [expanded, setExpanded] = useState<boolean>(!artifact.is_closed);
  const [componentValues, setComponentValues] = useState<Record<string, any>>(() => {
    const initial: Record<string, any> = {};
    const dataModel = (artifact.state?.dataModel || artifact.data || {}) as Record<string, any>;
    // Pre-populate values from body or existing dataModel
    const components = (artifact.body || (artifact.card as any)?.components || []) as Array<Record<string, any>>;
    for (const comp of components) {
      const compId = comp.id ? String(comp.id) : null;
      if (compId) {
        if (dataModel[compId] !== undefined) {
          initial[compId] = dataModel[compId];
        } else if (comp.value !== undefined) {
          initial[compId] = comp.value;
        }
      }
    }
    return initial;
  });

  // Comments for reviewable artifacts (LN:M format)
  const [comments, setComments] = useState<CommentRecord[]>([]);
  const [selectedRangeInfo, setSelectedRangeInfo] = useState<{
    location: string;
    text: string;
    rect: DOMRect | null;
  } | null>(null);
  const [commentInput, setCommentInput] = useState<string>("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Component lookup map by id
  const componentMap = useMemo(() => {
    const map = new Map<string, Record<string, any>>();
    const components = (artifact.body || (artifact.card as any)?.components || []) as Array<Record<string, any>>;
    for (const comp of components) {
      if (comp.id) {
        map.set(String(comp.id), comp);
      }
    }
    return map;
  }, [artifact.body, artifact.card]);

  // Root component
  const rootComponent = useMemo(() => {
    const components = artifact.body || (artifact.card as any)?.components || [];
    if (components.length === 0) return null;
    const root = components.find((c: any) => c.id === "root");
    return root || components[0];
  }, [artifact.body, artifact.card]);

  // Whitelisted buttons map from manifest
  const whitelistedButtons = useMemo(() => {
    const map = new Map<string, any>();
    for (const btn of artifact.manifest.buttons || []) {
      map.set(btn.id, btn);
    }
    return map;
  }, [artifact.manifest.buttons]);

  // Handle value change for inputs
  const handleValueChange = useCallback((componentId: string, value: any) => {
    if (isClosed) return;
    setComponentValues((prev) => ({
      ...prev,
      [componentId]: value,
    }));
  }, [isClosed]);

  // Text selection handler for inline commenting
  const handleMouseUp = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!isCommentable) return;
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) {
        return;
      }
      const text = selection.toString().trim();
      if (!text) return;

      // Calculate LN:M (Line N, Character M of target container)
      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      const containerText = e.currentTarget.innerText || "";
      const prefixText = containerText.slice(0, Math.max(0, containerText.indexOf(text)));
      const lines = prefixText.split("\n");
      const lineNum = lines.length;
      const charNum = (lines[lines.length - 1] || "").length + 1;
      const location = `L${lineNum}:${charNum}`;

      setSelectedRangeInfo({
        location,
        text,
        rect,
      });
      setCommentInput("");
    },
    [isCommentable]
  );

  const handleAddComment = () => {
    if (!selectedRangeInfo || !commentInput.trim()) return;
    const newComment: CommentRecord = {
      id: `comm_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      location: selectedRangeInfo.location,
      selectedText: selectedRangeInfo.text,
      comment: commentInput.trim(),
      timestamp: new Date().toISOString(),
    };
    setComments((prev) => [...prev, newComment]);
    setSelectedRangeInfo(null);
    setCommentInput("");
  };

  const handleRemoveComment = (id: string) => {
    setComments((prev) => prev.filter((c) => c.id !== id));
  };

  // Evaluate action event context payload dynamically
  const evaluateActionContext = useCallback(
    (action: any): Record<string, any> => {
      const result: Record<string, any> = {};
      const contextSpec = action?.event?.context || {};

      for (const [key, spec] of Object.entries(contextSpec)) {
        if (spec && typeof spec === "object" && typeof (spec as any).path === "string") {
          const path = (spec as any).path;
          if (path === "/review/comments") {
            result[key] = comments;
          } else if (path.startsWith("/components/")) {
            const parts = path.split("/");
            const compId = parts[2];
            const prop = parts[3] || "value";
            if (prop === "value") {
              result[key] = componentValues[compId] ?? componentMap.get(compId)?.value ?? null;
            } else {
              result[key] = componentMap.get(compId)?.[prop] ?? null;
            }
          } else {
            result[key] = spec;
          }
        } else {
          result[key] = spec;
        }
      }
      return result;
    },
    [componentValues, componentMap, comments]
  );

  // Button click dispatcher
  const handleButtonClick = async (btnComponent: any) => {
    if (isClosed || isSubmitting) return;
    const buttonId = btnComponent.id;
    const manifestBtn = whitelistedButtons.get(buttonId);

    // Whitelist check: If button not in manifest, drop with warning
    if (!manifestBtn) {
      console.warn(
        `[A2UI] Button "${buttonId}" clicked on artifact "${artifact.uuid}" is not listed in manifest.buttons. Ignoring.`
      );
      return;
    }

    // Quota check: If clicksLeft <= 0, button is inactive
    const clicksLeft = artifact.state?.clicksLeft?.[buttonId] ?? manifestBtn.clicks;
    if (typeof clicksLeft === "number" && clicksLeft <= 0) {
      console.warn(`[A2UI] Button "${buttonId}" has exhausted its click quota.`);
      return;
    }

    setSubmitError(null);
    const evaluatedContext = evaluateActionContext(btnComponent.action);

    try {
      if (onClickButton) {
        await onClickButton(buttonId, evaluatedContext);
      } else if (onSubmit) {
        await onSubmit({
          button_id: buttonId,
          ...evaluatedContext,
        });
      }
    } catch (err: any) {
      setSubmitError(err?.message || "Failed to process button click.");
    }
  };

  // Render individual component
  const renderComponent = (comp: any): React.ReactNode => {
    if (!comp) return null;
    const { id, component } = comp;

    switch (component) {
      case "Column": {
        const children = (comp.children || []).map((childId: string) =>
          componentMap.get(childId)
        );
        return (
          <div key={id} className="flex flex-col gap-3 w-full">
            {children.map((child: any) => child && renderComponent(child))}
          </div>
        );
      }

      case "Row": {
        const children = (comp.children || []).map((childId: string) =>
          componentMap.get(childId)
        );
        return (
          <div key={id} className="flex flex-row items-center gap-3 w-full flex-wrap">
            {children.map((child: any) => child && renderComponent(child))}
          </div>
        );
      }

      case "Card":
      case "Container": {
        const children = (comp.children || []).map((childId: string) =>
          componentMap.get(childId)
        );
        return (
          <div
            key={id}
            className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/60 shadow-sm w-full flex flex-col gap-3"
          >
            {children.map((child: any) => child && renderComponent(child))}
          </div>
        );
      }

      case "Text": {
        const variant = comp.variant || "body";
        const textContent = String(comp.text || "");

        if (variant === "h1") {
          return (
            <h1 key={id} className="text-xl font-bold text-zinc-100 tracking-tight">
              {textContent}
            </h1>
          );
        }
        if (variant === "h2") {
          return (
            <h2 key={id} className="text-lg font-semibold text-zinc-100 tracking-tight">
              {textContent}
            </h2>
          );
        }
        if (variant === "h3") {
          return (
            <h3 key={id} className="text-base font-semibold text-zinc-200">
              {textContent}
            </h3>
          );
        }
        if (variant === "bold") {
          return (
            <span key={id} className="font-semibold text-zinc-200 text-sm">
              {textContent}
            </span>
          );
        }
        if (variant === "caption") {
          return (
            <p key={id} className="text-xs text-zinc-400">
              {textContent}
            </p>
          );
        }

        // Default Markdown body text with selection capture for review
        return (
          <div
            key={id}
            onMouseUp={handleMouseUp}
            className="text-sm text-zinc-300 leading-relaxed max-w-none select-text cursor-text"
          >
            <MarkdownRenderer content={textContent} />
          </div>
        );
      }

      case "TextField": {
        const val = componentValues[id] ?? comp.value ?? "";
        return (
          <div key={id} className="flex flex-col gap-1.5 w-full">
            {comp.label && (
              <label className="text-xs font-medium text-zinc-300">{comp.label}</label>
            )}
            <input
              type="text"
              value={val}
              disabled={isClosed}
              placeholder={comp.placeholder || ""}
              onChange={(e) => handleValueChange(id, e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-zinc-950/80 border border-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
        );
      }

      case "ChoiceSet": {
        const isMulti = Boolean(comp.isMultiSelect);
        const choices = comp.choices || [];
        const currentVal = componentValues[id] ?? comp.value ?? (isMulti ? [] : "");

        const handleOptionToggle = (choiceVal: string) => {
          if (isClosed) return;
          if (isMulti) {
            const arr = Array.isArray(currentVal) ? [...currentVal] : [];
            const idx = arr.indexOf(choiceVal);
            if (idx >= 0) {
              arr.splice(idx, 1);
            } else {
              arr.push(choiceVal);
            }
            handleValueChange(id, arr);
          } else {
            handleValueChange(id, choiceVal);
          }
        };

        return (
          <div key={id} className="flex flex-col gap-2 w-full">
            {choices.map((choice: any) => {
              const selected = isMulti
                ? Array.isArray(currentVal) && currentVal.includes(choice.value)
                : currentVal === choice.value;

              return (
                <label
                  key={choice.id || choice.value}
                  className={`flex items-center gap-3 p-2.5 rounded-lg border transition-all cursor-pointer ${
                    selected
                      ? "bg-sky-500/10 border-sky-500/40 text-zinc-100"
                      : "bg-zinc-950/40 border-zinc-800/80 hover:bg-zinc-800/40 text-zinc-300"
                  } ${isClosed ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  <input
                    type={isMulti ? "checkbox" : "radio"}
                    name={id}
                    checked={selected}
                    disabled={isClosed}
                    onChange={() => handleOptionToggle(choice.value)}
                    className="accent-sky-500 size-4 cursor-pointer disabled:cursor-not-allowed"
                  />
                  <span className="text-sm font-medium">{choice.label || choice.value}</span>
                </label>
              );
            })}
          </div>
        );
      }

      case "Button": {
        const manifestBtn = whitelistedButtons.get(id);
        const clicksLeft = artifact.state?.clicksLeft?.[id] ?? manifestBtn?.clicks ?? "*";
        const isExhausted = typeof clicksLeft === "number" && clicksLeft <= 0;
        const isDisabled = isClosed || isSubmitting || !manifestBtn || isExhausted;

        const childComponent = comp.child ? componentMap.get(comp.child) : null;
        const labelText = childComponent?.text || comp.label || "Action";

        const variant = comp.variant || "primary";
        const btnClasses =
          variant === "danger"
            ? "bg-rose-600 hover:bg-rose-500 text-white"
            : variant === "secondary"
              ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700"
              : "bg-sky-600 hover:bg-sky-500 text-white";

        return (
          <button
            key={id}
            type="button"
            disabled={isDisabled}
            onClick={() => handleButtonClick(comp)}
            className={`px-4 py-2 rounded-lg font-medium text-sm transition-all shadow-sm flex items-center justify-center gap-2 ${btnClasses} ${
              isDisabled ? "opacity-50 cursor-not-allowed pointer-events-none" : ""
            }`}
          >
            {isClosed ? <Lock className="size-3.5 text-zinc-400" /> : null}
            <span>{labelText}</span>
            {typeof clicksLeft === "number" && clicksLeft > 0 && clicksLeft < 10 ? (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-black/30">
                {clicksLeft} left
              </span>
            ) : null}
          </button>
        );
      }

      case "Review": {
        const labelText = comp.label || "Submit Review Comments";
        const isDisabled = isClosed || isSubmitting;

        return (
          <div key={id} className="flex flex-col gap-3 w-full border-t border-zinc-800 pt-3">
            {comments.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="text-xs font-semibold text-zinc-400">
                  Review Comments ({comments.length})
                </span>
                <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
                  {comments.map((comm) => (
                    <div
                      key={comm.id}
                      className="p-2.5 rounded-lg bg-zinc-950/80 border border-zinc-800 flex items-start justify-between gap-2 text-xs"
                    >
                      <div className="flex flex-col gap-1">
                        <span className="font-mono text-[10px] text-sky-400 font-semibold">
                          {comm.location}
                        </span>
                        <p className="text-zinc-400 italic">"{comm.selectedText}"</p>
                        <p className="text-zinc-200 font-medium">{comm.comment}</p>
                      </div>
                      {!isClosed && (
                        <button
                          type="button"
                          onClick={() => handleRemoveComment(comm.id)}
                          className="text-zinc-500 hover:text-rose-400 transition-colors p-1"
                        >
                          <X className="size-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <button
              type="button"
              disabled={isDisabled || comments.length === 0}
              onClick={() => handleButtonClick(comp)}
              className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium text-sm flex items-center justify-center gap-2"
            >
              <MessageSquare className="size-4" />
              <span>{labelText}</span>
            </button>
          </div>
        );
      }

      default:
        return (
          <div key={id} className="text-xs text-zinc-500">
            [Unsupported component: {component}]
          </div>
        );
    }
  };

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
      className={`rounded-2xl border transition-all ${
        artifact.is_closed
          ? "bg-zinc-900/40 border-zinc-800/60"
          : artifact.manifest?.blocking
            ? "bg-zinc-900/90 border-sky-500/40 shadow-lg shadow-sky-950/20"
            : "bg-zinc-900/80 border-zinc-800"
      }`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/80">
        <div className="flex items-center gap-2.5">
          <div
            className={`p-1.5 rounded-lg ${
              artifact.is_closed
                ? "bg-zinc-800 text-zinc-400"
                : artifact.manifest?.blocking
                  ? "bg-sky-500/20 text-sky-400"
                  : "bg-zinc-800 text-zinc-200"
            }`}
          >
            {artifact.family === "plans" ? (
              <FileText className="size-4" />
            ) : (
              <Sparkles className="size-4" />
            )}
          </div>
          <span className="font-semibold text-sm text-zinc-100">{displayTitle}</span>
          {artifact.is_closed ? (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 font-medium flex items-center gap-1">
              <CheckCircle2 className="size-3 text-emerald-400" />
              Closed
            </span>
          ) : artifact.manifest?.blocking ? (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-300 font-medium">
              Blocking
            </span>
          ) : null}
        </div>

        {isEmbedded && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </button>
        )}
      </div>

      {/* Main body area */}
      {(!isEmbedded || expanded) && (
        <div className="p-4 flex flex-col gap-4 relative">
          {submitError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
              <AlertCircle className="size-4 shrink-0 text-rose-400" />
              <span>{submitError}</span>
            </div>
          )}

          {rootComponent ? (
            renderComponent(rootComponent)
          ) : (
            <p className="text-xs text-zinc-500">No components to display.</p>
          )}

          {/* Inline Comment Popover Modal */}
          {selectedRangeInfo && (
            <div
              className="absolute z-50 bg-zinc-900 border border-sky-500/40 rounded-xl p-3 shadow-2xl flex flex-col gap-2 w-72"
              style={{
                top: 40,
                right: 20,
              }}
            >
              <div className="flex items-center justify-between text-xs text-sky-300 font-semibold border-b border-zinc-800 pb-1.5">
                <span>Add Review Comment ({selectedRangeInfo.location})</span>
                <button
                  type="button"
                  onClick={() => setSelectedRangeInfo(null)}
                  className="text-zinc-500 hover:text-zinc-300"
                >
                  <X className="size-3.5" />
                </button>
              </div>
              <p className="text-[11px] text-zinc-400 italic line-clamp-2">
                "{selectedRangeInfo.text}"
              </p>
              <textarea
                value={commentInput}
                autoFocus
                onChange={(e) => setCommentInput(e.target.value)}
                placeholder="Enter feedback or change request..."
                rows={2}
                className="w-full text-xs p-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
              <button
                type="button"
                onClick={handleAddComment}
                disabled={!commentInput.trim()}
                className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-medium text-xs self-end"
              >
                Add Comment
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
