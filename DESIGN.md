---
name: PlantOps
description: Dense production control for Artemis Manufacturing — Plant 01.
colors:
  graphite: "#232e31"
  graphite-light: "#344246"
  floor: "#e1ded3"
  paper: "#f6f5ef"
  blue: "#466b7b"
  green: "#376b58"
  amber: "#805b20"
  red: "#993f35"
  ink: "#283638"
  muted: "#586361"
  line: "#bfc4ba"
typography:
  headline:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "22px"
    fontWeight: 600
    letterSpacing: "-0.02em"
  title:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "15px"
    fontWeight: 650
  body:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "13px"
    lineHeight: 1.6
  label:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "12px"
    fontWeight: 600
rounded:
  control: "2px"
  dialog: "3px"
spacing:
  space: "16px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "#fff"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "6px 11px"
  button-secondary:
    backgroundColor: "#f5f5ee"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "6px 11px"
  input:
    backgroundColor: "#fff"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "5px 8px"
  office-panel:
    backgroundColor: "{colors.paper}"
    padding: "24px"
---

# Design System: PlantOps

## Overview

**Creative North Star: "Production dispatch board"**

PlantOps inherits a serious MES/SCADA control-room interface. Dense readings, ruled tables, compact controls, and a top-down factory plan establish hierarchy through spacing, tone, and explicit labels. The existing implementation is the visual authority.

**Key Characteristics:**
- Charcoal navigation and warm, pale work surfaces.
- Operational color paired with readable state labels.
- Physical equipment geometry and restrained motion.

Source: `plantops-web/src/styles.css` and the components in `plantops-web/src/components/`. Surface-specific composition is recorded in `.impeccable/briefs/plantops-web.md`.

## Colors

### Primary

Steel blue (`blue`) identifies primary actions, maintenance, and structural emphasis.

### Secondary

Muted green (`green`) indicates running equipment; amber (`amber`) indicates queues and risk; operational red (`red`) identifies faults and errors. The SVG uses related state-specific fills and strokes from the stylesheet.

### Neutral

Charcoal (`graphite`, `graphite-light`) contains navigation and shift controls. Warm gray (`floor`) grounds the factory plan; pale paper (`paper`) holds work panels and dialogs. Dark ink, muted text, and subdued rules provide the remaining hierarchy.

## Typography

Segoe UI with Helvetica Neue, Arial, and sans-serif fallbacks is the interface stack. SVG text uses Segoe UI, Arial, and sans-serif. The hierarchy above records headings, prose, and controls; table text is compact (12px), with smaller headers and secondary readings (10–11px). Machine names and state labels carry more weight than equipment readouts. Numeric readings, clocks, tables, and inputs use tabular numerals. Consolas is limited to the report digest.

## Layout

The desktop shell combines a compact header with a left rail and a flexible central workspace. The default rail is 216px wide; workspaces have 20px horizontal padding. Panels use ruled sections and dense tables rather than separate cards for every metric.

At 1250px and below the header wraps and the rail narrows; at 850px and below the timeline hides and report sections stack. At 600px and below navigation becomes a horizontal scrolling strip above the workspace. The body minimum width is 360px. Tables and the factory plan scroll within their own containers; the map retains a minimum width of 1080px. Wide screens at 1600px and above use a 232px rail and 28px workspace padding.

## Elevation & Depth

There are no authored box shadows. Borders, surface tones, and SVG footprints create separation. Temporary native dialogs use a translucent charcoal backdrop (`rgb(23 34 34 / 50%)`), with no blur.

## Shapes

Work panels and tables are square. Buttons and inputs have minimally softened corners; dialogs use the slightly larger radius recorded above. Round status lamps and role-specific machine silhouettes convey physical equipment, rather than changing the interface's overall geometry.

## Components

- **Buttons and inputs:** Compact, bordered controls with a minimum height of 32px. Primary buttons use steel blue and white; secondary controls use pale surfaces. Hover changes background and border; disabled buttons reduce opacity. Keyboard focus uses a visible outline (2px with a 3px offset).
- **Navigation:** Full-width, left-aligned rows on charcoal; the current page has a lighter blue-gray background and visible border. Icons are inline outline SVGs beside text labels.
- **Panels and tables:** Pale surfaces, thin neutral borders, compact section headings, and ruled data rows. Late orders receive a warm warning tint. Status tags are small text labels, not pill containers.
- **Factory equipment:** Focusable SVG groups support click, Enter, and Space inspection. Each role has its own silhouette; selection and keyboard focus highlight the hit area. State lamps accompany explicit text. Queues retain numerical counts even when visible pallet stacks are capped.
- **Conveyors:** Dashed flow animates only on active routes (1.3s linear cycle). Pausing freezes it; blocked routes and reduced-motion preferences stop it. Route load, queue counts, and alerts reflect backend state.
- **Asset dialogs:** Temporary paper-toned native dialogs expose readings and actions. They have a close control and support Escape; inspection does not consume a permanent workspace column.

## Do's and Don'ts

### Do:
- **Do** preserve compact operational hierarchy and tabular readings.
- **Do** pair state colors with labels and show authoritative backend conditions.
- **Do** retain keyboard inspection and internal scrolling for the physical plan.

### Don't:
- **Don't** add gradients, glass, neon, emoji icons, or decorative SaaS cards.
- **Don't** replace the physical equipment plan with generic metric tiles.
- **Don't** use color or motion as the only way to communicate a state.

## V3 Living Shift Operations

The V3 operator surface extends the production dispatch board with a bounded, inspectable shift timeline. Seeded sessions expose three deterministic event records with stable IDs, effect windows, severity, workspace ownership, lifecycle state, and closure minute. The left rail and Plant View use the same projection for upcoming commitments, active notices, and receiving/dispatch markers; no event is created by rendering.

Office / Inbox keeps the handover and decision board concise. Decision cards state the live concern, measurable trade-off, owning workspace, current status, and whether a player decision was logged. Production Plan and Orders use a compact due-window chart backed by real release and due minutes; the chart scrolls internally on narrow screens. Reports distinguish provisional and final review, observed outcomes, intervention and labor/inspection/procurement costs, event history, and action history.

The three V3 controls are intentionally sparse and state-backed: one purchase-order expedite, one 60-minute overtime authorization with its documented fatigue exposure, and one quality containment activation on supported profiles. Quality presents ordinary scrap separately from modeled latent customer escapes and containment workload. Maintenance presents current exposure and service history. These decisions remain compact controls inside their relevant engineering workspace and inherit the existing square panels, ruled tables, and restrained operational palette.

Responsive behavior preserves the fixed factory plan as an internally scrollable physical map. Embedded order charts preserve their minimum readable row width through horizontal scrolling rather than expanding the page. Timeline secondary labels use the light charcoal-rail text token for readable contrast, and rejection meters carry equipment-specific accessible names.
