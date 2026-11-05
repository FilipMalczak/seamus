import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, ChevronUp, FileText, Loader2, Sparkles } from "lucide-react";
import * as AdaptiveCards from "adaptivecards";
import MarkdownIt from "markdown-it";
import type { ArtifactInfo } from "../api/types";

const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
});

AdaptiveCards.AdaptiveCard.onProcessMarkdown = (text, result) => {
  result.outputHtml = md.render(text);
  result.didProcess = true;
};

function createSeamusHostConfig(): AdaptiveCards.HostConfig {
  return new AdaptiveCards.HostConfig({
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    spacing: {
      small: 8,
      default: 12,
      medium: 16,
      large: 24,
      extraLarge: 32,
      padding: 16,
    },
    separator: {
      lineThickness: 1,
      lineColor: "#27272a",
    },
    containerStyles: {
      default: {
        backgroundColor: "#18181b",
        foregroundColors: {
          default: {
            default: "#f4f4f5",
            subtle: "#a1a1aa",
          },
          accent: {
            default: "#38bdf8",
            subtle: "#0284c7",
          },
          attention: {
            default: "#f87171",
            subtle: "#ef4444",
          },
          good: {
            default: "#34d399",
            subtle: "#10b981",
          },
          warning: {
            default: "#fbbf24",
            subtle: "#f59e0b",
          },
        },
      },
      emphasis: {
        backgroundColor: "#27272a",
        foregroundColors: {
          default: {
            default: "#f4f4f5",
            subtle: "#a1a1aa",
          },
          accent: {
            default: "#38bdf8",
            subtle: "#0284c7",
          },
        },
      },
    },
    actions: {
      actionsOrientation: "horizontal",
      actionAlignment: "stretch",
      buttonSpacing: 12,
      maxActions: 5,
      spacing: "large",
    },
  });
}

interface AdaptiveCardArtifactRendererProps {
  artifact: ArtifactInfo;
  onSubmit?: (data: Record<string, unknown>) => Promise<void> | void;
  isSubmitting?: boolean;
}

export function AdaptiveCardArtifactRenderer({
  artifact,
  onSubmit,
  isSubmitting = false,
}: AdaptiveCardArtifactRendererProps) {
  const cardContainerRef = useRef<HTMLDivElement>(null);
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

  useEffect(() => {
    if (!cardContainerRef.current) return;
    if (!artifact.card || Object.keys(artifact.card).length === 0) {
      setRenderError("Adaptive Card specification is missing.");
      return;
    }

    try {
      const adaptiveCard = new AdaptiveCards.AdaptiveCard();
      adaptiveCard.hostConfig = createSeamusHostConfig();

      adaptiveCard.onExecuteAction = (action: AdaptiveCards.Action) => {
        if (submittingRef.current || artifact.is_closed) return;
        if (action instanceof AdaptiveCards.SubmitAction) {
          const rawData = (action.data || {}) as Record<string, unknown>;
          const actionName = (rawData.action as string) || (rawData.event as any)?.name;

          if (onSubmit) {
            setSubmitError(null);
            const submissionPayload = { ...rawData };
            if (actionName) {
              submissionPayload.action = actionName;
            }
            Promise.resolve(onSubmit(submissionPayload)).catch((err: any) => {
              setSubmitError(err?.message || "Failed to submit artifact.");
            });
          }
        }
      };

      const cardPayload: any = JSON.parse(JSON.stringify(artifact.card));

      // When closed, strip submit action buttons and populate submitted values
      if (artifact.is_closed) {
        delete cardPayload.actions;

        const answers =
          (artifact.data as any)?.value ||
          (artifact.data as any)?.data ||
          artifact.data ||
          {};

        if (typeof answers === "object" && answers !== null) {
          const populateValues = (items: any[]) => {
            if (!Array.isArray(items)) return;
            for (const item of items) {
              if (item && typeof item === "object") {
                if (item.id && answers[item.id] !== undefined) {
                  item.value = String(answers[item.id] ?? "");
                }
                if (item.items) populateValues(item.items);
                if (item.columns) {
                  for (const col of item.columns) {
                    if (col && col.items) populateValues(col.items);
                  }
                }
              }
            }
          };
          if (cardPayload.body) {
            populateValues(cardPayload.body);
          }
        }
      }

      adaptiveCard.parse(cardPayload);

      const renderedCard = adaptiveCard.render();
      cardContainerRef.current.innerHTML = "";
      if (renderedCard) {
        cardContainerRef.current.appendChild(renderedCard);
      }
      setRenderError(null);
    } catch (err: any) {
      console.error("Failed to render Adaptive Card:", err);
      setRenderError(err?.message || "Failed to render Adaptive Card interface.");
    }
  }, [artifact.card, artifact.is_closed, artifact.data, onSubmit]);

  const isPlan = artifact.kind === "plans";
  const displayTitle =
    artifact.title ||
    artifact.manifest?.title ||
    (artifact.kind === "questionnaires"
      ? "Questionnaire"
      : artifact.kind === "forms"
        ? "Form"
        : artifact.kind === "plans"
          ? "Plan"
          : artifact.kind);

  return (
    <div
      className={`artifact-card ${artifact.is_closed ? "artifact-closed" : "artifact-open"} ${
        artifact.is_closed && !expanded ? "artifact-collapsed" : ""
      } ${isPlan ? "artifact-plan-card" : ""}`}
    >
      <div className="artifact-card-header">
        <div className="artifact-header-title">
          {isPlan ? (
            <FileText className="size-4 text-emerald-400" />
          ) : (
            <Sparkles className="size-4 text-sky-400" />
          )}
          <span className="font-semibold text-zinc-100">{displayTitle}</span>
          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-sky-400 border border-sky-400/20">
            Adaptive Card
          </span>
          {artifact.is_closed ? (
            <span className="artifact-status-badge closed">
              <CheckCircle2 className="size-3" />{" "}
              {isPlan ? "Ready to Execute" : "Submitted"}
            </span>
          ) : (
            <span className="artifact-status-badge active">
              {isPlan ? "Ready for Review" : "Action Required"}
            </span>
          )}
        </div>

        {artifact.is_closed && (
          <button
            type="button"
            className="artifact-collapse-toggle-btn"
            onClick={() => setExpanded((prev) => !prev)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <>
                <span>Hide details</span>
                <ChevronUp className="size-3.5" />
              </>
            ) : (
              <>
                <span>View details</span>
                <ChevronDown className="size-3.5" />
              </>
            )}
          </button>
        )}
      </div>

      {(!artifact.is_closed || expanded) && (
        <div
          className={`artifact-card-content ${
            artifact.is_closed ? "artifact-surface-disabled" : ""
          } ${isPlan ? "artifact-plan-content" : ""}`}
        >
          {renderError && (
            <div className="artifact-error-notice">
              <AlertCircle className="size-4 text-rose-400" />
              <span>{renderError}</span>
            </div>
          )}
          <div ref={cardContainerRef} className="adaptive-card-host" />
        </div>
      )}

      {isSubmitting && (
        <div className="artifact-submitting-overlay">
          <Loader2 className="size-4 animate-spin text-sky-400" />
          <span>Submitting...</span>
        </div>
      )}

      {submitError && <div className="artifact-error-notice">{submitError}</div>}
    </div>
  );
}
