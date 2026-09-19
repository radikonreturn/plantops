import { readStored, writeStored } from "../tutorial/state";

export interface AudioSettings {
  muted: boolean;
  master: number;
  ambience: number;
  alerts: number;
}
export type AudioCue = "objective" | "decisionNew" | "decisionDue" | "decisionExpired" | "decisionAccepted" | "failure" | "late" | "maintenanceStart" | "maintenanceEnd" | "delivery" | "due" | "flowWarning" | "production" | "shiftEnd" | "click";
export const defaultAudioSettings: AudioSettings = { muted: false, master: 0.32, ambience: 0.55, alerts: 0.65 };
const storageKey = "plantops.audio.v1";
export function normalizeSettings(value: Partial<AudioSettings> | null): AudioSettings {
  const level = (key: "master" | "ambience" | "alerts") => typeof value?.[key] === "number" && Number.isFinite(value[key]) ? Math.max(0, Math.min(1, value[key])) : defaultAudioSettings[key];
  return { muted: typeof value?.muted === "boolean" ? value.muted : false, master: level("master"), ambience: level("ambience"), alerts: level("alerts") };
}
export function readAudioSettings(): AudioSettings {
  try { return normalizeSettings(JSON.parse(readStored("localStorage", storageKey) ?? "null")); }
  catch { return { ...defaultAudioSettings }; }
}
export function saveAudioSettings(settings: AudioSettings): void {
  writeStored("localStorage", storageKey, JSON.stringify(normalizeSettings(settings)));
}

// A voice factory is the seam for future decoded .ogg/.mp3 buffer sources.
export interface AudioVoice {
  gain: GainNode;
  dispose: () => void;
}
export type VoiceFactory = (context: AudioContext, destination: AudioNode, machineId: string) => AudioVoice;
