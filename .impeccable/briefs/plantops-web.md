# PlantOps Web Direction Contract

## Mode

Operate. This is a control surface for running a factory shift, responding to exceptions, and making deterministic production decisions.

## World

A production dispatch board fused with a top-down factory routing plan. The interface should feel mounted in a control room: square steel-framed modules, ruled tables, compact legends, explicit labels, and a physical material-flow spine.

## First viewport

- Compact control strip: plant identity, shift clock, playback controls, small operational KPIs, and New Shift. Replay seed lives in an advanced dialog section.
- Dominant factory-floor map: raw warehouse through CNC, Wash, Assembly, Quality, and finished goods.
- Permanent left rail: timeline, live concerns and eight engineering workspaces. No permanent right inspector.
- Order dispatch board below the map on desktop.

## Signature

The line itself is the primary visualization. A continuous conveyor spine, work-zone boundaries, warehouse racks, buffer counters, flow arrows, and status-coded machine footprints make the current bottleneck readable without opening another view.

## Visual rules

- Charcoal control chrome, warm-gray floor, steel-blue structure, muted green normal operation, amber constraints, red faults only.
- No gradients, glass, glow, decorative illustrations, floating cards, or oversized marketing typography.
- Square corners or minimal 2 px radii; hierarchy comes from rules, spacing, tone, and label weight.
- Tabular numerals for clocks, counts, rates, and costs.
- Motion is reserved for active conveyors and running machine indicators; reduced-motion users get static equivalents.

## Direction selection

The assigned production-traveler/dispatch-board concept is the committed direction. Challenger concepts contributed only useful traits: aircraft instruments reinforced immediate state identification, orienteering maps reinforced a fixed legend and spatial hierarchy, and Crouwel-style specimens reinforced disciplined alignment. Their visual idioms are otherwise rejected because they would weaken the explicit MES/SCADA setting.

## Responsive behavior

Desktop is authoritative. The 1220-unit SVG map fits the full central workspace at 1440 px; at narrow widths it scrolls internally. Office screens replace the central canvas within the same shell. Equipment details use a temporary keyboard-accessible dialog. The left rail becomes a horizontal workspace strip on phones.
