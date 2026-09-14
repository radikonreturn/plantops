# PlantOps Web Direction Contract

## Mode

Operate. This is a control surface for running a factory shift, responding to exceptions, and making deterministic production decisions.

## World

A production dispatch board fused with a top-down factory routing plan. The interface should feel mounted in a control room: square steel-framed modules, ruled tables, compact legends, explicit labels, and a physical material-flow spine.

## First viewport

- Persistent control strip: plant identity, shift clock, playback controls, replay seed, and six primary KPIs.
- Dominant factory-floor map: raw warehouse through CNC, Wash, Assembly, Quality, and finished goods.
- Operations rail: selected equipment actions, procurement, costs, and alerts.
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

Desktop is authoritative. Below 1100 px, factory floor, operations, and orders stack. The production line remains a horizontally scrollable spatial model instead of collapsing into generic cards.
