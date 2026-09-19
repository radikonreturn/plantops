import { readStored, writeStored } from "../tutorial/state";
import { en, type TranslationKey } from "./en";
import { tr } from "./tr";

export type Locale = "en" | "tr";
export type Values = Record<string, string | number | null | undefined>;
export interface Message { key: TranslationKey; values?: Values }
export const message = (key: TranslationKey, values?: Values): Message => ({ key, values });
export const isLocale = (value: unknown): value is Locale => value === "en" || value === "tr";
export const readLocale = (): Locale => {
  const saved = readStored("localStorage", "plantops.locale");
  return isLocale(saved) ? saved : "en";
};
export function persistLocale(locale: Locale): void {
  writeStored("localStorage", "plantops.locale", locale);
}

export function translate(locale: Locale, key: TranslationKey, values: Values = {}): string {
  const template = Object.prototype.hasOwnProperty.call(en, key)
    ? (locale === "tr" ? tr[key] : en[key]) ?? en[key]
    : key;
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    Object.prototype.hasOwnProperty.call(values, name) ? String(values[name] ?? "") : placeholder
  );
}

// Exact dictionary lookup for backend enums without a separate display identifier.
// Unknown values keep their original text; there is no substring translation.
export function knownText(locale: Locale, original: string): string {
  return Object.prototype.hasOwnProperty.call(en, original)
    ? translate(locale, original as TranslationKey)
    : original;
}
export function resolveMessage(locale: Locale, value: Message | string | null): string | null {
  return value === null ? null : typeof value === "string" ? knownText(locale, value) : translate(locale, value.key, value.values);
}
export function statusLabel(locale: Locale, value: string): string {
  // Only these uppercase enums are display statuses; event codes stay verbatim.
  const states = ["IDLE", "RUNNING", "STARVED", "BLOCKED", "DOWN", "PLANNED_MAINTENANCE", "PENDING", "ACTIVE", "LATE", "COMPLETED_ON_TIME", "COMPLETED_LATE", "OPEN", "RECEIVED_ON_TIME", "RECEIVED_LATE"];
  if (value === value.toUpperCase() && !states.includes(value)) return value;
  const key = value.toLowerCase().replace(/_/g, " ");
  return Object.prototype.hasOwnProperty.call(en, key) ? knownText(locale, key) : value;
}
