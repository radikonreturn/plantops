import { useI18n } from "../i18n";
import type { PlantAudio } from "./usePlantAudio";

export function AudioControls({ audio }: { audio: PlantAudio }) {
  const { t } = useI18n();
  const { settings, activated, updateSettings } = audio;
  return <div className="audio-controls" data-audio-controls>
    <button type="button" aria-label={t(settings.muted ? "Unmute" : "Mute")} title={t(settings.muted ? "Unmute" : "Mute")} aria-pressed={settings.muted} onClick={() => updateSettings({ ...settings, muted: !settings.muted })}>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4Z" />{settings.muted ? <path d="m17 9 5 6m0-6-5 6" /> : <path d="M16 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" />}</svg>
    </button>
    <details className="audio-settings"><summary>{t("Sound")}</summary>
      <div className="audio-panel">
        {([['master', 'Master volume'], ['ambience', 'Ambience'], ['alerts', 'Alerts']] as const).map(([key, label]) => <label key={key}>
          <span>{t(label)} <output>{Math.round(settings[key] * 100)}%</output></span>
          <input type="range" min="0" max="100" step="1" value={Math.round(settings[key] * 100)} onChange={event => updateSettings({ ...settings, [key]: Number(event.target.value) / 100 })} />
        </label>)}
        {!activated && <p>{t("Sound starts after your first interaction")}</p>}
      </div>
    </details>
  </div>;
}
