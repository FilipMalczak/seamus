---
name: a2ui_components
description: Canonical reference for authoring A2UI basic catalog components (Text, TextField, ChoiceSet, Button, Column, Row, Card, Container, Review) and action payloads in Seamus artifacts.
---

# A2UI Basic Catalog Reference

Seamus utilizes a clean subset of the **A2UI Basic Catalog (v0.9)** for describing declarative user interfaces in artifacts. The full component definition JSON schema is stored in `./resources/catalog.json`.

Artifact UI definitions reside in `/artifacts/<family>/<uuid>/body.json` as a flat JSON array of component objects matching the structure expected in A2UI `updateComponents` events.

## Core Component Types

### 1. `Text`
Renders formatted text or headers.
```json
{
  "id": "intro_title",
  "component": "Text",
  "text": "Please choose your deployment settings",
  "variant": "h2"
}
```
- `text`: String value or Markdown text.
- `variant`: `"h1" | "h2" | "h3" | "h4" | "h5" | "body" | "caption" | "bold"`

### 2. `TextField`
Single-line or multi-line text input field.
```json
{
  "id": "custom_note_input",
  "component": "TextField",
  "label": "Additional Notes",
  "placeholder": "Enter custom details...",
  "value": ""
}
```
- `value`: Current text string. Evaluated on click via path context `/components/<id>/value`.

### 3. `ChoiceSet`
Single-choice or multi-choice options set (radio buttons or checkboxes).
```json
{
  "id": "env_choices",
  "component": "ChoiceSet",
  "isMultiSelect": false,
  "choices": [
    { "id": "opt_staging", "label": "Staging", "value": "staging" },
    { "id": "opt_prod", "label": "Production", "value": "production" }
  ],
  "value": "staging"
}
```
- `isMultiSelect`: Boolean (`false` for radio buttons, `true` for checkboxes).
- `choices`: Array of `{ "id": str, "label": str, "value": str }`.
- `value`: Current selected value (string for single select, array of strings for multi-select).

### 4. `Button`
Clickable button initiating an action event.
```json
{
  "id": "submit-btn",
  "component": "Button",
  "child": "submit_label",
  "variant": "primary",
  "action": {
    "event": {
      "name": "submit_settings",
      "context": {
        "environment": { "path": "/components/env_choices/value" },
        "notes": { "path": "/components/custom_note_input/value" }
      }
    }
  }
}
```
- `id`: Button ID. **Must be listed in `manifest.json` under `buttons`**, or clicks will be ignored!
- `child`: ID of child `Text` component providing the label.
- `variant`: `"primary" | "secondary" | "danger"`
- `action.event.context`: Dictionary mapping output keys to JSON pointers (e.g. `/components/<component_id>/value`). Evaluated when the button is clicked.

### 5. Layout Containers: `Column`, `Row`, `Container`, `Card`
Organize child components visually.
```json
{
  "id": "root",
  "component": "Column",
  "children": ["intro_title", "env_choices", "custom_note_input", "submit-btn"]
}
```
- `children`: List of component IDs rendered within this container.

### 6. `Review`
Dedicated inline commenting and review component used for reviewing document artifacts (such as plans).
```json
{
  "id": "review-btn",
  "component": "Review",
  "target": "plan_content",
  "label": "Submit Review Comments",
  "action": {
    "event": {
      "name": "review_comments",
      "context": {
        "comments": { "path": "/review/comments" }
      }
    }
  }
}
```
When clicked, comments formatted with `LN:M` line-and-character coordinates are pushed into `/interactions/<id>.json`.

