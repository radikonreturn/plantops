import { clock } from "../format";
import { useI18n } from "../i18n";
import { resolveMessage } from "../i18n/core";
import type { Workspace } from "../types";
import type { DecisionFeedback } from "./feedback";

export function DecisionFeedbackCard({ result, dismiss, navigate }: { result: DecisionFeedback; dismiss: () => void; navigate: (view: Workspace) => void }) {
  const { t, label, locale } = useI18n();
  return <section className="decision-feedback" role="status" aria-live="polite">
    <div className="section-title"><div><h2>{t("What changed?")}</h2><strong>{resolveMessage(locale, result.title)}</strong><small>{clock(result.minute)}</small></div><button onClick={dismiss}>{t("Dismiss")}</button></div>
    <h3>{t("Immediate changes")}</h3>
    <dl className="decision-changes">{result.changes.map((change, index) => <div key={index}><dt>{t(change.label)}{change.id && ` · ${change.id}`}</dt><dd>{typeof change.before === "string" ? label(change.before) : change.before} → {typeof change.after === "string" ? label(change.after) : change.after}</dd></div>)}</dl>
    {result.expected.length > 0 && <><h3>{t("Expected, not guaranteed")}</h3>{[...new Set(result.expected)].map(text => <p key={text}>{t(text)}</p>)}</>}
    <button onClick={() => navigate(result.workspace)}>{t("Open {value1}", { value1: t(result.workspace) })}</button>
  </section>;
}
