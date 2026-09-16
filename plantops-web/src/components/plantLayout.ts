import type { AssetConfig } from "../types";

// Fixed physical equipment bays, keyed by role. Seeds never alter the building.
// Each inlet includes a queue footprint and a conveyor into its machine.
export const equipmentBays: Record<AssetConfig["stage_role"], {x: number; y: number; queueX: number; queueY: number}> = {
  laser: {x: 280, y: 120, queueX: 30, queueY: 110},
  cnc: {x: 555, y: 120, queueX: 463, queueY: 100},
  wash: {x: 830, y: 120, queueX: 738, queueY: 100},
  assembly: {x: 480, y: 430, queueX: 660, queueY: 422},
  test: {x: 755, y: 430, queueX: 663, queueY: 515},
  quality: {x: 1030, y: 430, queueX: 938, queueY: 422},
};
