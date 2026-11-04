import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, ChevronUp, Loader2, Sparkles } from "lucide-react";
import { MessageProcessor, type ProcessableMessage } from "@a2ui/web_core/v0_9";
import { basicCatalog } from "@a2ui/web_core/v0_9/basic_catalog";
import { A2uiSurface } from "@a2ui/react/v0_9";
import type { ArtifactInfo } from "../api/types";

interface A2uiArtifactRendererProps {
  artifact: ArtifactInfo;
  onSubmit?: (data: Record<string, unknown>) => Promise<void> | void;
  isSubmitting?: boolean;
}

export function A2uiArtifactRenderer({
  artifact,
  onSubmit,
  isSubmitting = false,
}: A2uiArtifactRendererProps) {
  const [surfaceModel, setSurfaceModel] = useState<any>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<boolean>(!artifact.is_closed);
  const submittingRef = useRef<boolean>(false);
  submittingRef.current = isSubmitting;

  const wasClosedRef = useRef<boolean>(artifact.is_closed);
  useEffect(() => {
    if (!wasClosedRef.current && artifact.is_closed) {
      setExpanded(false);
    }
    wasClosedRef.current = artifact.is_closed;
  }, [artifact.is_closed]);

  const aliasCatalog = useMemo(() => {
    try {
      return (basicCatalog as any).derive({
        catalogId: "https://a2ui.org/specification/v0_9/basic_catalog.json",
      });
    } catch {
      return null;
    }
  }, []);

  const processor = useMemo(() => {
    const catalogs = aliasCatalog
      ? [basicCatalog as any, aliasCatalog as any]
      : [basicCatalog as any];

    return new MessageProcessor(catalogs, (action) => {
      if (submittingRef.current) return;
      if (artifact.is_closed) return;

      const actionName = (action as any)?.name || (action as any)?.event?.name;
      const context = (action as any)?.context || (action as any)?.event?.context || {};

      if (actionName === "submit_questionnaire" || !actionName) {
        if (onSubmit) {
          setSubmitError(null);
          Promise.resolve(onSubmit(context)).catch((err: any) => {
            setSubmitError(err?.message || "Failed to submit questionnaire.");
          });
        }
      }
    });
  }, [aliasCatalog, artifact.is_closed, onSubmit]);

  useEffect(() => {
    if (!processor) return;
    try {
      const messages: ProcessableMessage[] = [];
      if (artifact.surface) {
        messages.push(artifact.surface as ProcessableMessage);
      }
      if (artifact.components) {
        messages.push(artifact.components as ProcessableMessage);
      }
      if (artifact.data) {
        messages.push(artifact.data as ProcessableMessage);
      }
      processor.processMessages(messages);
      const surface = processor.model.getSurface("surface");
      if (!surface) {
        throw new Error("A2UI surface 'surface' could not be resolved from messages.");
      }
      setSurfaceModel(surface);
      setRenderError(null);
    } catch (err: any) {
      console.error("Failed to process A2UI messages:", err);
      setRenderError(err?.message || "Failed to render A2UI interface.");
    }
  }, [processor, artifact.surface, artifact.components, artifact.data]);

  return (
    <div
      className={`a2ui-artifact-card ${artifact.is_closed ? "a2ui-closed" : "a2ui-open"} ${
        artifact.is_closed && !expanded ? "a2ui-collapsed" : ""
      }`}
    >
      <div className="a2ui-card-header">
        <div className="a2ui-header-title">
          <Sparkles className="size-4 text-sky-400" />
          <span className="font-semibold text-zinc-100">
            {artifact.kind === "questionnaires" ? "Questionnaire" : artifact.kind}
          </span>
          {artifact.is_closed ? (
            <span className="a2ui-status-badge closed">
              <CheckCircle2 className="size-3" /> Submitted
            </span>
          ) : (
            <span className="a2ui-status-badge active">Action Required</span>
          )}
        </div>

        {artifact.is_closed && (
          <button
            type="button"
            className="a2ui-collapse-toggle-btn"
            onClick={() => setExpanded((prev) => !prev)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <>
                <span>Hide submitted answers</span>
                <ChevronUp className="size-3.5" />
              </>
            ) : (
              <>
                <span>View submitted answers</span>
                <ChevronDown className="size-3.5" />
              </>
            )}
          </button>
        )}
      </div>

      {(!artifact.is_closed || expanded) && (
        <div className={`a2ui-card-content ${artifact.is_closed ? "a2ui-surface-disabled" : ""}`}>
          {renderError ? (
            <div className="a2ui-error-notice">
              <AlertCircle className="size-4 text-rose-400" />
              <span>{renderError}</span>
            </div>
          ) : surfaceModel ? (
            <A2uiSurface surface={surfaceModel} />
          ) : (
            <div className="a2ui-loading">
              <Loader2 className="size-4 animate-spin text-sky-400" />
              <span>Rendering interface...</span>
            </div>
          )}
        </div>
      )}

      {isSubmitting && (
        <div className="a2ui-submitting-overlay">
          <Loader2 className="size-4 animate-spin text-sky-400" />
          <span>Submitting your answers...</span>
        </div>
      )}

      {submitError && <div className="a2ui-error-notice">{submitError}</div>}
    </div>
  );
}
