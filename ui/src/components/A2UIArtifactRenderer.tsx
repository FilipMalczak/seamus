import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { A2uiSurface, MarkdownContext } from "@a2ui/react";
import { MessageProcessor, basicCatalog, setMarkdownRenderer } from "@a2ui/web_core/v1_0";
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

const CANONICAL_COMPONENT_MAP: Record<string, string> = {
  text: "Text",
  heading: "Text",
  header: "Text",
  paragraph: "Text",
  label: "Text",
  button: "Button",
  btn: "Button",
  column: "Column",
  col: "Column",
  row: "Row",
  card: "Card",
  divider: "Divider",
  separator: "Divider",
  image: "Image",
  img: "Image",
  tabs: "Tabs",
  modal: "Modal",
  dialog: "Modal",
  choicepicker: "ChoicePicker",
  choiceset: "ChoicePicker",
  select: "ChoicePicker",
  dropdown: "ChoicePicker",
  radio: "ChoicePicker",
  radiogroup: "ChoicePicker",
  textfield: "TextField",
  textinput: "TextField",
  input: "TextField",
  checkbox: "CheckBox",
  slider: "Slider",
  datetimeinput: "DateTimeInput",
  dateinput: "DateTimeInput",
};

const COMPONENT_TYPE_ALIAS_KEYS = ["type", "component_type", "componentType", "widget", "kind"];

function toValidUax31Identifier(id: string): string {
  if (!id) return "comp";
  let clean = id.trim().replace(/[-\s\.]+/g, "_");
  clean = clean.replace(/[^\p{XID_Continue}_]/gu, "_");
  if (clean && /^\p{Nd}/u.test(clean)) {
    clean = `_${clean}`;
  }
  clean = clean.replace(/_+/g, "_");
  if (!clean || !/^[\p{XID_Start}_][\p{XID_Continue}]*$/u.test(clean)) {
    clean = clean ? `comp_${clean}` : "comp";
  }
  return clean;
}

/**
 * Normalizes components into standard A2UI basicCatalog specifications.
 * Seamlessly adapts legacy or custom shapes (like ChoiceSet -> ChoicePicker, Text variant 'bold' -> Markdown body).
 */
function normalizeComponents(components: any): Array<Record<string, any>> {
  let rawList = components;
  if (typeof rawList === "string") {
    try {
      rawList = JSON.parse(rawList);
    } catch {
      return [];
    }
  }

  if (rawList && typeof rawList === "object" && !Array.isArray(rawList)) {
    if (Array.isArray(rawList.components)) {
      rawList = rawList.components;
    } else if (Array.isArray(rawList.body)) {
      rawList = rawList.body;
    } else if (rawList.surface && Array.isArray(rawList.surface.components)) {
      rawList = rawList.surface.components;
    } else {
      rawList = [rawList];
    }
  }

  if (!Array.isArray(rawList)) {
    return [];
  }

  const existingIds = new Set<string>();
  for (const item of rawList) {
    if (item && typeof item === "object" && typeof item.id === "string" && item.id.trim()) {
      existingIds.add(item.id.trim());
    }
  }

  const extraComponents: Array<Record<string, any>> = [];
  const seenIdsInPass = new Set<string>();
  const idRemap: Record<string, string> = {};

  const normalized: Array<Record<string, any>> = [];

  for (let idx = 0; idx < rawList.length; idx++) {
    const comp = rawList[idx];
    if (!comp || typeof comp !== "object") {
      normalized.push(comp);
      continue;
    }

    const c = { ...comp };

    // 1. Alias resolution for component type
    if (!c.component || typeof c.component !== "string") {
      for (const aliasKey of COMPONENT_TYPE_ALIAS_KEYS) {
        if (typeof c[aliasKey] === "string" && c[aliasKey].trim()) {
          c.component = c[aliasKey].trim();
          delete c[aliasKey];
          break;
        }
      }
    }

    // Property-based component type inference
    if (!c.component || typeof c.component !== "string") {
      if (typeof c.text === "string") {
        c.component = "Text";
      } else if (Array.isArray(c.options) || Array.isArray(c.choices)) {
        c.component = "ChoicePicker";
      } else if (Array.isArray(c.children)) {
        c.component = "Column";
      } else if (typeof c.child === "string") {
        c.component = "Card";
      } else if (typeof c.url === "string" || typeof c.src === "string") {
        c.component = "Image";
      } else if (Array.isArray(c.tabs)) {
        c.component = "Tabs";
      } else if (c.action) {
        c.component = "Button";
      } else if (c.validationRegexp) {
        c.component = "TextField";
      }
    }

    // Canonicalize component type
    if (typeof c.component === "string") {
      const orig = c.component;
      const canon = CANONICAL_COMPONENT_MAP[orig.toLowerCase()];
      if (canon) {
        c.component = canon;
        if (["heading", "header"].includes(orig.toLowerCase())) {
          c.variant = "body";
          if (typeof c.text === "string" && !c.text.startsWith("#")) {
            c.text = `## ${c.text}`;
          }
        }
      }
    }

    // 2. ID resolution: Auto-assign ID if missing or empty, normalize to UAX #31
    if (!c.id || typeof c.id !== "string" || !c.id.trim()) {
      const prefix = toValidUax31Identifier(String(c.component || "comp").toLowerCase());
      let candidate = `${prefix}_${idx}`;
      let counter = 1;
      while (existingIds.has(candidate)) {
        candidate = `${prefix}_${idx}_${counter}`;
        counter++;
      }
      existingIds.add(candidate);
      c.id = candidate;
    } else {
      const origId = c.id.trim();
      let candidate = origId;
      if (!/^[\p{XID_Start}_][\p{XID_Continue}]*$/u.test(candidate)) {
        candidate = toValidUax31Identifier(origId);
        idRemap[origId] = candidate;
      }

      if (seenIdsInPass.has(candidate)) {
        let dedupCand = `${candidate}_${idx}`;
        let counter = 1;
        while (existingIds.has(dedupCand)) {
          dedupCand = `${candidate}_${idx}_${counter}`;
          counter++;
        }
        existingIds.add(dedupCand);
        c.id = dedupCand;
        idRemap[origId] = dedupCand;
      } else {
        seenIdsInPass.add(candidate);
        existingIds.delete(origId);
        existingIds.add(candidate);
        c.id = candidate;
      }
    }

    // 3. Component-specific adaptations
    if (c.component === "Text") {
      let variant = c.variant;
      let text = c.text;
      if (text === undefined || text === null) {
        for (const alias of ["content", "body", "value", "label"]) {
          if (c[alias] !== undefined) {
            text = String(c[alias]);
            delete c[alias];
            break;
          }
        }
      }
      if (text === undefined || text === null) text = "";

      if (variant === "bold") {
        variant = "body";
        if (typeof text === "string" && !text.startsWith("**")) {
          text = `**${text}**`;
        }
      } else if (["h1", "h2", "h3", "h4", "h5"].includes(variant)) {
        const level = parseInt(variant[1], 10);
        const prefix = "#".repeat(level) + " ";
        if (typeof text === "string" && !text.startsWith("#")) {
          text = `${prefix}${text}`;
        }
        variant = "body";
      } else if (!["caption", "body"].includes(variant)) {
        variant = "body";
      }
      normalized.push({ ...c, variant, text });
      continue;
    }

    if (c.component === "ChoiceSet" || c.component === "ChoicePicker") {
      const isMulti = Boolean(c.isMultiSelect || c.variant === "multipleSelection");
      const options = (c.choices || c.options || []).map((opt: any) => ({
        label: opt.label || opt.text || opt.value || opt.id || "",
        value: String(opt.value || opt.id || ""),
      }));
      let val = c.value;
      if (val && typeof val === "object" && "path" in val) {
        // Data model pointer: preserve { path: "..." }
      } else if (Array.isArray(val)) {
        val = val.map(String);
      } else if (val !== undefined && val !== null && val !== "") {
        val = [String(val)];
      } else {
        val = [];
      }
      normalized.push({
        id: c.id,
        component: "ChoicePicker",
        variant: isMulti ? "multipleSelection" : "mutuallyExclusive",
        options,
        value: val,
      });
      continue;
    }

    if (c.component === "TextInput" || c.component === "TextField") {
      let val = c.value;
      if (val && typeof val === "object" && "path" in val) {
        // Data model pointer: preserve { path: "..." }
      } else if (val === undefined || val === null) {
        val = "";
      }
      normalized.push({
        id: c.id,
        component: "TextField",
        label: c.label || c.placeholder || c.id || "",
        value: val,
      });
      continue;
    }

    if (c.component === "Button") {
      let variant = c.variant;
      if (variant && !["default", "primary", "borderless"].includes(variant)) {
        variant = "default";
      }
      const action = c.action || {
        event: {
          name: c.id || "button_click",
          context: {},
        },
      };
      if (
        action.event &&
        typeof action.event === "object" &&
        action.event.context &&
        typeof action.event.context === "object"
      ) {
        const cleanContext: Record<string, any> = {};
        for (const [k, v] of Object.entries(action.event.context)) {
          if (!(v && typeof v === "object" && "path" in (v as any))) {
            cleanContext[k] = v;
          }
        }
        action.event.context = cleanContext;
      }

      if (!c.child || typeof c.child !== "string") {
        const labelText = c.label || c.text || c.title || c.id || "Button";
        let btnLabelId = `${c.id}_label`;
        let counter = 1;
        while (existingIds.has(btnLabelId)) {
          btnLabelId = `${c.id}_label_${counter}`;
          counter++;
        }
        existingIds.add(btnLabelId);
        extraComponents.push({
          id: btnLabelId,
          component: "Text",
          text: String(labelText),
        });
        c.child = btnLabelId;
      }

      normalized.push({
        ...c,
        action,
        ...(variant ? { variant } : {}),
      });
      continue;
    }

    if (c.component === "Card") {
      if (!c.child || typeof c.child !== "string") {
        if (Array.isArray(c.children)) {
          if (c.children.length === 1 && typeof c.children[0] === "string") {
            c.child = c.children[0];
          } else {
            let cardColId = `${c.id}_col`;
            let counter = 1;
            while (existingIds.has(cardColId)) {
              cardColId = `${c.id}_col_${counter}`;
              counter++;
            }
            existingIds.add(cardColId);
            extraComponents.push({
              id: cardColId,
              component: "Column",
              children: c.children,
            });
            c.child = cardColId;
          }
        } else if (c.title || c.body || c.content) {
          const innerIds: string[] = [];
          if (c.title) {
            let tId = `${c.id}_title`;
            let counter = 1;
            while (existingIds.has(tId)) {
              tId = `${c.id}_title_${counter}`;
              counter++;
            }
            existingIds.add(tId);
            extraComponents.push({
              id: tId,
              component: "Text",
              text: `### ${String(c.title)}`,
              variant: "body",
            });
            innerIds.push(tId);
          }
          const bodyVal = c.body || c.content;
          if (bodyVal) {
            if (typeof bodyVal === "string" && existingIds.has(bodyVal)) {
              innerIds.push(bodyVal);
            } else {
              let bId = `${c.id}_body`;
              let counter = 1;
              while (existingIds.has(bId)) {
                bId = `${c.id}_body_${counter}`;
                counter++;
              }
              existingIds.add(bId);
              extraComponents.push({
                id: bId,
                component: "Text",
                text: String(bodyVal),
                variant: "body",
              });
              innerIds.push(bId);
            }
          }
          let cardColId = `${c.id}_col`;
          let counter = 1;
          while (existingIds.has(cardColId)) {
            cardColId = `${c.id}_col_${counter}`;
            counter++;
          }
          existingIds.add(cardColId);
          extraComponents.push({
            id: cardColId,
            component: "Column",
            children: innerIds,
          });
          c.child = cardColId;
        } else {
          let emptyId = `${c.id}_empty`;
          let counter = 1;
          while (existingIds.has(emptyId)) {
            emptyId = `${c.id}_empty_${counter}`;
            counter++;
          }
          existingIds.add(emptyId);
          extraComponents.push({
            id: emptyId,
            component: "Text",
            text: "",
          });
          c.child = emptyId;
        }
      }
      normalized.push(c);
      continue;
    }

    if (c.component === "Column" || c.component === "Row") {
      if (!Array.isArray(c.children)) {
        if (typeof c.child === "string") {
          c.children = [c.child];
          delete c.child;
        } else {
          c.children = [];
        }
      }
      normalized.push(c);
      continue;
    }

    if (c.component === "Image") {
      if (c.src && !c.url) {
        c.url = c.src;
        delete c.src;
      }
      normalized.push(c);
      continue;
    }

    normalized.push(c);
  }

  normalized.push(...extraComponents);

  if (Object.keys(idRemap).length > 0) {
    for (const comp of normalized) {
      if (!comp || typeof comp !== "object") continue;
      if (typeof comp.child === "string" && idRemap[comp.child]) {
        comp.child = idRemap[comp.child];
      }
      if (Array.isArray(comp.children)) {
        comp.children = comp.children.map((ch: any) =>
          typeof ch === "string" && idRemap[ch] ? idRemap[ch] : ch
        );
      }
      if (typeof comp.trigger === "string" && idRemap[comp.trigger]) {
        comp.trigger = idRemap[comp.trigger];
      }
      if (typeof comp.content === "string" && idRemap[comp.content]) {
        comp.content = idRemap[comp.content];
      }
      if (Array.isArray(comp.tabs)) {
        for (const t of comp.tabs) {
          if (t && typeof t.child === "string" && idRemap[t.child]) {
            t.child = idRemap[t.child];
          }
        }
      }
      if (comp.action && typeof comp.action === "object") {
        const event = comp.action.event;
        if (event && typeof event === "object" && event.context && typeof event.context === "object") {
          const newCtx: Record<string, any> = {};
          for (const [k, v] of Object.entries(event.context)) {
            const newK = idRemap[k] || k;
            if (v && typeof v === "object" && typeof (v as any).path === "string") {
              let p = (v as any).path;
              for (const [oldK, newV] of Object.entries(idRemap)) {
                p = p.replace(new RegExp(`/${oldK}/`, "g"), `/${newV}/`);
                if (p.endsWith(`/${oldK}`)) {
                  p = p.slice(0, -oldK.length) + newV;
                }
              }
              newCtx[newK] = { ...(v as any), path: p };
            } else {
              newCtx[newK] = v;
            }
          }
          event.context = newCtx;
        }
      }
    }
  }

  // Ensure there is a root component for A2UI MessageProcessor/NodeResolver
  const hasRoot = normalized.some((c: any) => c && c.id === "root");
  if (!hasRoot && normalized.length > 0) {
    const referenced = new Set<string>();
    for (const c of normalized) {
      if (!c) continue;
      if (typeof c.child === "string") referenced.add(c.child);
      if (Array.isArray(c.children)) {
        for (const ch of c.children) {
          if (typeof ch === "string") referenced.add(ch);
        }
      }
      if (typeof c.trigger === "string") referenced.add(c.trigger);
      if (typeof c.content === "string") referenced.add(c.content);
      if (Array.isArray(c.tabs)) {
        for (const t of c.tabs) {
          if (t && typeof t.child === "string") referenced.add(t.child);
        }
      }
    }
    const roots = normalized.filter((c: any) => c && c.id && !referenced.has(c.id)).map((c: any) => c.id);
    if (roots.length > 0) {
      normalized.unshift({
        id: "root",
        component: "Column",
        children: roots,
      });
    }
  }

  return normalized;
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

function collectInputSnapshot(container: HTMLElement | null): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  if (!container) return result;

  const elements = Array.from(container.querySelectorAll("*"));
  for (const el of elements) {
    const customEl = el as any;
    const node = customEl.node;
    const compId =
      node?.componentId ||
      customEl.context?.componentModel?.id ||
      customEl.getAttribute?.("data-component-id");
    const compType = node?.type || customEl.getAttribute?.("data-component-type");
    if (!compId || !compType) continue;

    if (compType === "TextField" || compType === "TextInput") {
      const input = customEl.querySelector("input, textarea") as HTMLInputElement | HTMLTextAreaElement | null;
      result[compId] = input ? input.value : (customEl.controller?.props?.value ?? "");
    } else if (compType === "CheckBox") {
      const checkbox = customEl.querySelector("input[type='checkbox']") as HTMLInputElement | null;
      result[compId] = checkbox ? checkbox.checked : Boolean(customEl.controller?.props?.value);
    } else if (compType === "ChoicePicker" || compType === "ChoiceSet") {
      const isMulti =
        node?.properties?.variant === "multipleSelection" ||
        node?.properties?.isMultiSelect ||
        customEl.controller?.props?.variant === "multipleSelection" ||
        customEl.controller?.props?.isMultiSelect ||
        customEl.querySelector("input[type='checkbox']") !== null;
      const checkedInputs = Array.from(
        customEl.querySelectorAll("input:checked")
      ) as HTMLInputElement[];
      const selectedChips = Array.from(
        customEl.querySelectorAll(".a2ui-chip-selected")
      ) as HTMLElement[];

      if (isMulti) {
        const vals: string[] = [];
        checkedInputs.forEach((inp) => {
          if (inp.value) vals.push(inp.value);
        });
        selectedChips.forEach((chip) => {
          const v = chip.getAttribute("data-value") || chip.textContent?.trim();
          if (v && !vals.includes(v)) vals.push(v);
        });
        result[compId] = vals;
      } else {
        const checkedRadio = customEl.querySelector("input[type='radio']:checked") as HTMLInputElement | null;
        const select = customEl.querySelector("select") as HTMLSelectElement | null;
        if (checkedRadio) {
          result[compId] = checkedRadio.value;
        } else if (select) {
          result[compId] = select.value;
        } else if (checkedInputs.length > 0) {
          result[compId] = checkedInputs[0].value;
        } else if (selectedChips.length > 0) {
          result[compId] =
            selectedChips[0].getAttribute("data-value") || selectedChips[0].textContent?.trim() || "";
        } else {
          result[compId] = customEl.controller?.props?.value ?? "";
        }
      }
    } else if (compType === "Slider") {
      const slider = customEl.querySelector("input[type='range']") as HTMLInputElement | null;
      result[compId] = slider ? Number(slider.value) : Number(customEl.controller?.props?.value ?? 0);
    } else if (compType === "DateTimeInput") {
      const dt = customEl.querySelector("input") as HTMLInputElement | null;
      result[compId] = dt ? dt.value : (customEl.controller?.props?.value ?? "");
    }
  }

  return result;
}

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
      const manifestBtn = (curArtifact.manifest?.buttons || []).find(
        (b) => b.id === buttonId || b.id.replace(/-/g, "_") === buttonId.replace(/-/g, "_")
      );
      if (!manifestBtn) {
        console.warn(`[A2UI] Button "${buttonId}" clicked but not declared in manifest.`);
        return;
      }

      const effectiveBtnId = manifestBtn.id;
      const clicksLeft =
        curArtifact.state?.clicksLeft?.[buttonId] ?? curArtifact.state?.clicksLeft?.[effectiveBtnId];
      if (typeof clicksLeft === "number" && clicksLeft <= 0) {
        console.warn(`[A2UI] Button "${buttonId}" has exhausted clicks.`);
        return;
      }

      // 1. Gather static context
      const rawCtx = (action.context || {}) as Record<string, unknown>;
      const staticContext: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(rawCtx)) {
        if (!(v && typeof v === "object" && "path" in (v as any))) {
          staticContext[k] = v;
        }
      }

      const bodyComp = (curArtifact.body || []).find((c) => c && c.id === buttonId);
      const btnAction = (bodyComp as any)?.action as any;
      if (btnAction?.event?.context && typeof btnAction.event.context === "object") {
        for (const [k, v] of Object.entries(btnAction.event.context)) {
          if (!(v && typeof v === "object" && "path" in (v as any))) {
            staticContext[k] = v;
          }
        }
      }

      // 2. Snapshot all input widgets from the DOM container
      const inputSnapshot = collectInputSnapshot(contentContainerRef.current);

      // 3. Comments handling
      let attachedComments: Array<Record<string, unknown>> | undefined;
      const isPushComments =
        btnAction?.comments === "push" ||
        buttonId === "review_btn" ||
        buttonId === "review-btn" ||
        (curIsCommentable && curComments.length > 0);
      if (isPushComments && curComments.length > 0) {
        attachedComments = curComments.map((c) => ({
          location: c.location,
          selectedText: c.selectedText,
          comment: c.comment,
        }));
      }

      const eventName =
        action.name ||
        btnAction?.event?.name ||
        buttonId;

      const clickPayload: Record<string, unknown> = {
        button_id: buttonId,
        event: eventName,
        timestamp: new Date().toISOString(),
        ...(Object.keys(staticContext).length > 0 ? { context: staticContext } : {}),
        ...(Object.keys(inputSnapshot).length > 0 ? { data: inputSnapshot } : {}),
        ...(attachedComments && attachedComments.length > 0 ? { comments: attachedComments } : {}),
      };

      try {
        curOnClickButton?.(buttonId, clickPayload);
        const submitPromise = curOnSubmit?.(clickPayload);
        if (isPushComments) {
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
          version: "1.0",
          createSurface: {
            surfaceId,
            catalogId: basicCatalog.id,
          },
        },
        {
          version: "1.0",
          updateDataModel: {
            surfaceId,
            path: "/",
            value: artifact.state?.dataModel || artifact.data || {},
          },
        },
        {
          version: "1.0",
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
            version: "1.0",
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
