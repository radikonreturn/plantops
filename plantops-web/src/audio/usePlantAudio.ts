import { useEffect, useRef, useState } from "react";
import type { SessionSnapshot } from "../types";
import { AudioEngine } from "./AudioEngine";
import { readAudioSettings, saveAudioSettings, type AudioSettings } from "./audioTypes";

export function bindAudioInteractions(engine: AudioEngine, target: Document, activated: () => void): () => void {
  let attached = true;
  const interact = (event: Event) => {
    if (!event.isTrusted) return;
    const key = event as KeyboardEvent;
    if (event.type === "keydown" && (key.repeat || key.ctrlKey || key.metaKey || key.altKey || !["Enter", " ", "Tab"].includes(key.key))) return;
    const element = event.target instanceof Element ? event.target : null;
    if (element?.closest('input, textarea, select, [contenteditable="true"], [role="slider"]')) return;
    const button = element?.closest("button");
    if (button?.disabled || button?.getAttribute("aria-disabled") === "true") return;
    void engine.activate().then(active => { if (attached && active) activated(); });
    // Keyboard activation produces one native click too; only that click is sonified.
    if (event.type === "click" && button && !button.closest('.speed-group, [data-audio-controls]')) engine.playCue("click");
  };
  const visibility = () => engine.setHidden(target.hidden);
  target.addEventListener("click", interact, true);
  target.addEventListener("keydown", interact, true);
  target.addEventListener("visibilitychange", visibility);
  visibility();
  return () => {
    attached = false;
    target.removeEventListener("click", interact, true);
    target.removeEventListener("keydown", interact, true);
    target.removeEventListener("visibilitychange", visibility);
  };
}
export function usePlantAudio(snapshot: SessionSnapshot | null, connectionHold: boolean) {
  const [settings, setSettings] = useState(readAudioSettings);
  const [activated, setActivated] = useState(false);
  const engine = useRef<AudioEngine | null>(null);
  const latestSettings = useRef(settings);
  latestSettings.current = settings;
  useEffect(() => {
    const instance = new AudioEngine(latestSettings.current);
    engine.current = instance;
    const unbind = bindAudioInteractions(instance, document, () => setActivated(true));
    return () => { unbind(); instance.dispose(); engine.current = null; };
  }, []);
  useEffect(() => { engine.current?.process(snapshot, connectionHold); }, [snapshot, connectionHold]);
  useEffect(() => { engine.current?.setSettings(settings); }, [settings]);
  const updateSettings = (next: AudioSettings) => {
    // Apply mute before React's next effect and persist through the safe storage boundary.
    engine.current?.setSettings(next); setSettings(next); saveAudioSettings(next);
  };
  return { settings, activated, updateSettings };
}
export type PlantAudio = ReturnType<typeof usePlantAudio>;
