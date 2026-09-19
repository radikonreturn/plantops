import type { SessionSnapshot } from "../types";
import { defaultAudioSettings, normalizeSettings, type AudioCue, type AudioSettings, type AudioVoice, type VoiceFactory } from "./audioTypes";
import { createMachineVoice } from "./machineProfiles";
import { audioFrame, audioTransitions, cuePriority, type AudioFrame } from "./snapshotAudio";

const tones: Record<AudioCue, [number, number, number]> = {
  objective: [410, 610, .23], decisionNew: [360, 460, .13], decisionDue: [410, 370, .15], decisionExpired: [310, 220, .2], decisionAccepted: [440, 540, .12],
  failure: [190, 125, 0.38], late: [330, 240, 0.28],
  maintenanceStart: [140, 85, 0.18], maintenanceEnd: [390, 520, 0.22],
  delivery: [260, 370, 0.24], due: [420, 390, 0.16],
  flowWarning: [290, 270, 0.12], production: [650, 720, 0.09],
  shiftEnd: [520, 260, 0.65], click: [480, 350, 0.025],
};
const cooldown: Partial<Record<AudioCue, number>> = { failure: 8000, late: 15000, production: 20000, flowWarning: 20000, due: 30000, click: 100 };
const browserContext = (): AudioContext | null => {
  if (typeof window === "undefined") return null;
  const Constructor = window.AudioContext ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  return Constructor ? new Constructor() : null;
};

export class AudioEngine {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private ambience: GainNode | null = null;
  private alerts: GainNode | null = null;
  private voices = new Map<string, AudioVoice>();
  private shots = new Set<() => void>();
  private previous: AudioFrame | null = null;
  private settings: AudioSettings;
  private hidden = false;
  private resync = false;
  private hold = false;
  private disposed = false;
  private activating: Promise<boolean> | null = null;
  private lastCue = new Map<AudioCue, number>();
  private lastAlert = -Infinity;

  constructor(settings: AudioSettings = defaultAudioSettings, private createContext = browserContext, private now = () => performance.now(), private voiceFactory: VoiceFactory = createMachineVoice) {
    this.settings = normalizeSettings(settings);
  }
  get active(): boolean { return this.context?.state === "running" && !this.disposed; }

  // Called only by the trusted interaction boundary, never by render/snapshot effects.
  activate(): Promise<boolean> {
    if (this.disposed || this.hidden) return Promise.resolve(false);
    if (this.active) return Promise.resolve(true);
    if (this.activating) return this.activating;
    this.activating = this.start().finally(() => { this.activating = null; });
    return this.activating;
  }
  private async start(): Promise<boolean> {
    try {
      if (!this.context) {
        this.context = this.createContext();
        if (!this.context) return false;
        this.master = this.context.createGain(); this.master.gain.value = 0;
        this.ambience = this.context.createGain(); this.ambience.gain.value = 0;
        this.alerts = this.context.createGain(); this.alerts.gain.value = 0;
        this.ambience.connect(this.master); this.alerts.connect(this.master); this.master.connect(this.context.destination);
      }
      if (this.context.state !== "running") await this.context.resume();
      if (this.disposed) return false;
      this.applySettings(); this.syncLoops();
      return this.active;
    } catch { this.releaseContext(); return false; }
  }
  setSettings(settings: AudioSettings): void {
    this.settings = normalizeSettings(settings);
    this.safely(() => { this.applySettings(); });
  }
  private ramp(param: AudioParam, value: number, seconds = 0.18): void {
    const time = this.context!.currentTime;
    if (typeof param.cancelAndHoldAtTime === "function") param.cancelAndHoldAtTime(time);
    else { param.cancelScheduledValues(time); param.setValueAtTime(param.value, time); }
    param.linearRampToValueAtTime(value, time + seconds);
  }
  private applySettings(): void {
    if (!this.master || !this.ambience || !this.alerts) return;
    // Mute is immediate, including sources already scheduled or starting this frame.
    if (this.settings.muted || this.hidden) {
      this.master.gain.cancelScheduledValues(this.context!.currentTime);
      this.master.gain.setValueAtTime(0, this.context!.currentTime);
      this.clearShots();
    } else this.ramp(this.master.gain, this.settings.master);
    this.ramp(this.ambience.gain, this.settings.ambience);
    this.ramp(this.alerts.gain, this.settings.alerts);
  }
  process(snapshot: SessionSnapshot | null, connectionHold = false): void {
    this.safely(() => {
      if (this.hold !== connectionHold) this.resync = true;
      this.hold = connectionHold;
      if (!snapshot) { this.previous = null; this.stopLoops(); this.clearShots(); return; }
      const next = audioFrame(snapshot);
      const old = this.previous;
      const reset = !old || old.session !== next.session || next.minute < old.minute;
      this.previous = next;
      if (reset) { this.lastCue.clear(); this.lastAlert = -Infinity; this.stopLoops(); this.clearShots(); }
      this.syncLoops();
      const skip = reset || this.resync || this.hidden || this.hold || !this.active;
      this.resync = false;
      if (skip || !old) return;
      const events = audioTransitions(old, next);
      // Intentionally discard lower priorities: no delayed alarm backlog.
      const chosen = cuePriority.find(cue => events.includes(cue));
      if (chosen) this.playCue(chosen);
    });
  }
  setHidden(hidden: boolean): void {
    this.hidden = hidden;
    this.resync = true;
    this.safely(() => {
      this.applySettings();
      if (hidden) this.stopLoops();
      else this.syncLoops();
    });
  }
  private syncLoops(): void {
    if (!this.context || !this.ambience || !this.active) return;
    const frame = this.previous;
    if (!frame || frame.paused || frame.ended || this.hold || this.hidden) { this.stopLoops(); return; }
    const ids = new Set([...Object.keys(frame.machines), "conveyor"]);
    for (const [id, voice] of this.voices) if (!ids.has(id)) { voice.dispose(); this.voices.delete(id); }
    for (const id of ids) {
      let voice = this.voices.get(id);
      if (!voice) { voice = this.voiceFactory(this.context, this.ambience, id); this.voices.set(id, voice); }
      const state = frame.machines[id]?.state;
      const level = id === "conveyor" ? (frame.conveyor ? 1 : 0) : state === "RUNNING" ? 1 : state === "IDLE" ? 0.12 : state === "STARVED" || state === "BLOCKED" ? 0.06 : 0;
      this.ramp(voice.gain.gain, level, state === "DOWN" ? 0.04 : 0.35);
    }
  }
  playCue(cue: AudioCue): void {
    this.safely(() => {
      if (!this.active || !this.alerts || this.hidden || this.settings.muted || this.settings.master === 0 || this.settings.alerts === 0) return;
      const now = this.now();
      if (now - (this.lastCue.get(cue) ?? -Infinity) < (cooldown[cue] ?? 6000)) return;
      if (cue !== "click" && now - this.lastAlert < 1500) return;
      this.lastCue.set(cue, now);
      if (cue !== "click") this.lastAlert = now;
      const context = this.context!;
      const source = context.createOscillator();
      const gain = context.createGain();
      const dispose = () => { source.onended = null; try { source.stop(); } catch { /* Already stopped. */ } source.disconnect(); gain.disconnect(); this.shots.delete(dispose); };
      this.shots.add(dispose);
      const [from, to, duration] = tones[cue];
      const time = context.currentTime;
      gain.gain.value = 0;
      source.type = cue === "maintenanceStart" ? "triangle" : "sine";
      source.frequency.setValueAtTime(from, time); source.frequency.exponentialRampToValueAtTime(to, time + duration);
      gain.gain.setValueAtTime(0, time);
      gain.gain.linearRampToValueAtTime(cue === "click" || cue === "production" ? 0.035 : 0.12, time + 0.012);
      gain.gain.linearRampToValueAtTime(0, time + duration);
      source.connect(gain); gain.connect(this.alerts); source.onended = dispose;
      source.start(); source.stop(time + duration + 0.02);
    });
  }
  private clearShots(): void { for (const dispose of this.shots) dispose(); this.shots.clear(); }
  private stopLoops(): void { for (const voice of this.voices.values()) voice.dispose(); this.voices.clear(); }
  private safely(action: () => void): void { if (this.disposed) return; try { action(); } catch { this.releaseContext(); } }
  private releaseContext(): void {
    try { this.stopLoops(); this.clearShots(); this.master?.disconnect(); this.ambience?.disconnect(); this.alerts?.disconnect(); } catch { /* Context loss must never reach gameplay. */ }
    const context = this.context;
    this.context = null; this.master = null; this.ambience = null; this.alerts = null;
    try { void context?.close().catch(() => {}); } catch { /* Unsupported/closed context. */ }
  }
  dispose(): void { this.disposed = true; this.previous = null; this.releaseContext(); }
}
