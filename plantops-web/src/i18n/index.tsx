import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { persistLocale, readLocale, statusLabel, translate, type Locale, type Values } from "./core";
import type { TranslationKey } from "./en";

export function createTranslator(locale: Locale) {
  return {
    locale,
    t: (key: TranslationKey, values?: Values) => translate(locale, key, values),
    label: (value: string) => statusLabel(locale, value),
    money: (value: number) => value.toLocaleString(locale === "tr" ? "tr-TR" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    percent: (value: number | null) => value === null ? "—" : new Intl.NumberFormat(locale === "tr" ? "tr-TR" : "en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value),
  };
}
const I18nContext = createContext({ ...createTranslator("en"), setLocale: (_locale: Locale) => {} });
export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, updateLocale] = useState<Locale>(readLocale);
  const value = useMemo(() => ({ ...createTranslator(locale), setLocale: (next: Locale) => {
    updateLocale(next);
    persistLocale(next);
  } }), [locale]);
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
export const useI18n = () => useContext(I18nContext);

export function LanguageSelector() {
  const { locale, setLocale, t } = useI18n();
  return <select className="language-selector" aria-label={t("Language")} value={locale}
    onChange={event => setLocale(event.target.value === "tr" ? "tr" : "en")}>
    <option value="en" lang="en">English</option>
    <option value="tr" lang="tr">Türkçe</option>
  </select>;
}
