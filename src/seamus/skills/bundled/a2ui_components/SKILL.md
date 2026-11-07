---
name: a2ui_components
description: Canonical reference for authoring A2UI basic catalog components (Text, TextField, ChoicePicker, Button, Column, Row, Card, Divider) and root hierarchy in Seamus artifacts.
---

# A2UI Basic Catalog Reference

Seamus utilizes the **A2UI Basic Catalog (v0.9)** for describing declarative user interfaces in artifacts. The full component definition JSON schema is stored in `./resources/catalog.json`.

Artifact UI definitions reside in `/artifacts/<family>/<uuid>/body.json` as a flat JSON array of component objects matching the structure expected in A2UI `updateComponents` events.

---

## The Mandatory Root Component Rule

> [!IMPORTANT]
> **One component in `components` MUST have `"id": "root"`** (typically a `Column`, `Row`, or `Card`).
> 
> A2UI resolves and renders component trees starting from the component with `id="root"`. All other components in the flat array must be direct or indirect descendants of this root component (referenced by ID in `children: ["..."]` or `child: "..."`).
>
> If multiple widgets are emitted without an enclosing root container (e.g. emitting a `Text` and a `Button` side-by-side with no parent), the component structure is incomplete and will trigger a warning.

```mermaid
graph TD
    Root["root (Column)"] --> Intro["intro (Text)"]
    Root --> CardWidget["card1 (Card)"]
    Root --> ActionRow["actions (Row)"]
    CardWidget --> FormCol["form_col (Column)"]
    FormCol --> Input["name_field (TextField)"]
    FormCol --> Choices["env_picker (ChoicePicker)"]
    ActionRow --> SubmitBtn["submit_btn (Button)"]
    SubmitBtn --> SubmitLbl["submit_lbl (Text)"]
```

---

## Component Reference

### 1. Root & Layout Containers

#### `Column`
Vertical stack layout container.
```json
{
  "id": "root",
  "component": "Column",
  "children": ["title_text", "settings_card", "actions_row"]
}
```
- `children`: Array of component IDs rendered vertically in order.
- `justify`: (Optional) `"start" | "center" | "end" | "spaceBetween" | "spaceAround" | "spaceEvenly"`
- `align`: (Optional) `"start" | "center" | "end" | "stretch" | "baseline"`

#### `Row`
Horizontal layout container.
```json
{
  "id": "actions_row",
  "component": "Row",
  "children": ["cancel_btn", "submit_btn"]
}
```
- `children`: Array of component IDs rendered horizontally in order.
- `justify`, `align`: Same options as `Column`.

#### `Card`
Visually framed panel card.
```json
{
  "id": "settings_card",
  "component": "Card",
  "child": "settings_column"
}
```
> [!CAUTION]
> In A2UI v0.9, `Card` strictly accepts a single child ID (`"child": "<id>"`). It **does NOT** accept `title` or `body`. To create a card with a title and multiple fields, point `child` to a `Column` containing a `Text` title and your content components.

#### `Divider`
Visual dividing line.
```json
{
  "id": "divider_1",
  "component": "Divider",
  "axis": "horizontal"
}
```
- `axis`: `"horizontal" | "vertical"` (defaults to `"horizontal"`).

---

### 2. Display Components

#### `Text`
Renders formatted text, markdown, or headings.
```json
{
  "id": "intro_title",
  "component": "Text",
  "text": "## Deployment Configuration",
  "variant": "body"
}
```
- `text`: String value (supports GitHub-flavored Markdown).
- `variant`: `"h1" | "h2" | "h3" | "h4" | "h5" | "body" | "caption"`

#### `Image`
Renders an image from a URL.
```json
{
  "id": "banner",
  "component": "Image",
  "url": "https://example.com/logo.png",
  "fit": "contain"
}
```
- `url`: Image source URL string.
- `fit`: `"contain" | "cover" | "fill" | "none" | "scaleDown"`

#### `Icon`
Renders a named icon.
```json
{
  "id": "check_icon",
  "component": "Icon",
  "name": "check"
}
```

---

### 3. Input & Interactive Components

#### `TextField`
Text entry field for user input.
```json
{
  "id": "notes_input",
  "component": "TextField",
  "label": "Release Notes",
  "value": ""
}
```
- `label`: Label describing the field.
- `value`: Initial string value (or data model binding).
- `variant`: (Optional) `"shortText" | "longText" | "number" | "obscured"`

#### `ChoicePicker` (or `ChoiceSet`)
Single or multiple choice selection.
```json
{
  "id": "env_picker",
  "component": "ChoicePicker",
  "label": "Target Environment",
  "variant": "mutuallyExclusive",
  "options": [
    { "label": "Staging", "value": "staging" },
    { "label": "Production", "value": "production" }
  ],
  "value": ["staging"]
}
```
- `options`: List of `{ "label": str, "value": str }`.
- `variant`: `"mutuallyExclusive"` (radio buttons) or `"multipleSelection"` (checkboxes).
- `value`: List of selected value strings.

#### `Button`
Clickable action button.
```json
{
  "id": "deploy-btn",
  "component": "Button",
  "child": "deploy_btn_label",
  "variant": "primary",
  "action": {
    "event": {
      "name": "deploy_action",
      "context": {
        "environment": { "path": "/components/env_picker/value" },
        "notes": { "path": "/components/notes_input/value" }
      }
    }
  }
}
```
- `id`: Button ID. **MUST be declared in `manifest.json` under `buttons`**, or clicks will be ignored!
- `child`: String ID of a child component providing the label (typically a `Text` component).
- `variant`: `"primary"` (main action), `"default"` (secondary/neutral), `"borderless"` (link style).
- `action`: Action payload containing the event name and context data pointers.

---

## Complete Example: Showcase Custom Artifact

Here is a complete, working example of an artifact showcasing widgets properly structured under a root container:

### `manifest.json`
```json
{
  "name": "Widget Showcase",
  "exposition": "embedded",
  "blocking": false,
  "commentable": false,
  "buttons": [
    {
      "id": "submit-btn",
      "mode": "set",
      "clicks": 1,
      "unblocking": false,
      "closing": false
    }
  ]
}
```

### `body.json`
```json
[
  {
    "id": "root",
    "component": "Column",
    "children": ["header_text", "config_card", "actions_row"]
  },
  {
    "id": "header_text",
    "component": "Text",
    "text": "### Custom Widget Showcase\nConfigure your options below.",
    "variant": "body"
  },
  {
    "id": "config_card",
    "component": "Card",
    "child": "card_column"
  },
  {
    "id": "card_column",
    "component": "Column",
    "children": ["target_picker", "notes_field"]
  },
  {
    "id": "target_picker",
    "component": "ChoicePicker",
    "label": "Select Target",
    "variant": "mutuallyExclusive",
    "options": [
      { "label": "Development", "value": "dev" },
      { "label": "Staging", "value": "staging" }
    ],
    "value": ["dev"]
  },
  {
    "id": "notes_field",
    "component": "TextField",
    "label": "Additional Notes",
    "value": ""
  },
  {
    "id": "actions_row",
    "component": "Row",
    "children": ["submit-btn"]
  },
  {
    "id": "submit-btn",
    "component": "Button",
    "child": "submit_label",
    "variant": "primary",
    "action": {
      "event": {
        "name": "submit_showcase",
        "context": {
          "target": { "path": "/components/target_picker/value" },
          "notes": { "path": "/components/notes_field/value" }
        }
      }
    }
  },
  {
    "id": "submit_label",
    "component": "Text",
    "text": "Submit Configuration"
  }
]
```
